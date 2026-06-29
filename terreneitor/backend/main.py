import os
import time

import sentry_sdk
from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from terreneitor.backend import (
    rutas_admin,
    rutas_auth,
    rutas_gerencia,
    rutas_health,
    rutas_ia,
    rutas_reportes,
    rutas_scanner,
    rutas_supervisor,
    rutas_terreno,
)
from terreneitor.backend.core.dependencias import get_db_hash
from terreneitor.backend.core.nucleo import SessionLocal, app, engine
from terreneitor.backend.models.modelos import Base, User, UserRoleEnum
from terreneitor.backend.utils.logger import log

# --- Sentry: monitoreo de errores en produccion ---
# Si SENTRY_DSN no esta seteado, Sentry queda inactivo (no rompe nada).
# Cuando se setea, el SDK envia automaticamente:
# - Excepciones no capturadas en handlers FastAPI.
# - Trazas de performance (subsampleadas para no inundar el plan free).
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
if SENTRY_DSN:
    env = os.environ.get("ENV", "development").strip().lower()
    # En prod: 10% de trazas (suficiente para detectar lentitud sin saturar).
    # En dev: 100% para debugging local.
    traces_rate = 0.1 if env in {"prod", "production"} else 1.0

    def _scrub_pii(event, _hint):
        """Quita campos sensibles antes de enviar a Sentry."""
        # No enviar el body de requests (puede contener passwords del login).
        if "request" in event and "data" in event.get("request", {}):
            event["request"]["data"] = "[scrubbed]"
        # No enviar cookies (incluyen el JWT de sesion).
        if "request" in event and "cookies" in event.get("request", {}):
            event["request"]["cookies"] = "[scrubbed]"
        return event

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env,
        traces_sample_rate=traces_rate,
        send_default_pii=False,
        before_send=_scrub_pii,
        # Identificar la version de la app (commit hash o tag).
        release=os.environ.get("APP_VERSION") or os.environ.get("GIT_SHA"),
    )
    log.info("[SENTRY] Inicializado (env=%s, traces=%.0f%%)", env, traces_rate * 100)
else:
    log.info("[SENTRY] Inactivo (SENTRY_DSN no configurado)")

# Seguridad y Rate Limiting
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from terreneitor.backend.core.dependencias import limiter  # noqa: E402

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Routers
app.include_router(rutas_admin.router)

# Middleware de Performance (Mide tiempo de respuesta)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    # Log con contexto (request_id podria agregarse aqui si existiera middleware de ids)
    log.info(f"REQ {request.method} {request.url.path} - {process_time:.4f}s")

    response.headers["X-Process-Time"] = str(process_time)

    # SECURITY HEADERS (Fase 5)
    response.headers["X-Frame-Options"] = "DENY"  # Anti-clickjacking
    response.headers["X-Content-Type-Options"] = "nosniff"  # Anti-MIME sniffing
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains"  # Force HTTPS
    )

    return response
    return response


# --- REDIRECTS A MODULOS ---
@app.get("/portal.html", include_in_schema=False)
async def portal_redirect():
    # El portal/admin se eliminó (la administración se hace desde la config de Monstruo).
    # Se mantiene el path viejo redirigiendo a gerencia para no romper enlaces guardados.
    return RedirectResponse(url="/modulos/gerencia/")


@app.get("/terreno.html", include_in_schema=False)
async def terreno_redirect():
    return RedirectResponse(url="/modulos/terreno/")


@app.get("/supervisor.html", include_in_schema=False)
async def supervisor_redirect():
    return RedirectResponse(url="/modulos/supervisor/")


@app.get("/gerencia.html", include_in_schema=False)
async def gerencia_redirect():
    return RedirectResponse(url="/modulos/gerencia/")


# URL única del módulo: terreneitor.telconsulting.cl sirve el HUB (entrada con
# tarjetas por rol); los módulos viven en paths /modulos/<m>/ bajo ese host.
SUBDOMAIN_MODULES = {
    "terreneitor.telconsulting.cl": "hub",
}

# Subdominios antiguos -> redirigen a la URL única (transición a módulo Monstruo)
LEGACY_HOSTS = {
    "terreno.telconsulting.cl",
    "portal.telconsulting.cl",
    "supervisor.telconsulting.cl",
    "gerencial.telconsulting.cl",
}


def _env_prefix() -> str:
    return "/dev" if os.environ.get("ENV", "").lower() in ("dev", "development") else ""


_FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "ui")
)


@app.get("/", include_in_schema=False)
async def root_handler(request: Request):
    """URL única: la raíz redirige al HUB (o el host legacy al host único).

    Redirige en vez de servir HTML: el proxy inyecta <base> en la raíz exacta
    (config histórica por subdominio) y rompía los assets del hub. En
    /modulos/hub/ no hay inyección y las rutas relativas resuelven solas.
    La Location relativa preserva el prefijo de entorno (/dev) sin conocerlo.
    """
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    host = host.split(",")[0].strip().split(":")[0].lower()
    if host in LEGACY_HOSTS:
        return RedirectResponse(
            url=f"https://terreneitor.telconsulting.cl{_env_prefix()}/"
        )
    module = SUBDOMAIN_MODULES.get(host, "hub")
    return RedirectResponse(url=f"modulos/{module}/")


@app.get("/login.html", include_in_schema=False)
async def login_redirect():
    return RedirectResponse(url="/modulos/login/")


@app.get("/shared/{asset_path:path}", include_in_schema=False)
def shared_assets_proxy(asset_path: str):
    """Sirve los assets compartidos del gateway de Monstruo (misma red docker).

    Así el hub usa la barra IDÉNTICA del ecosistema (monstruo.css, sidebar.js,
    utilidades.js) sin copias locales que se desactualicen, y same-origin
    (sin CORS ni líos de prefijo /dev).
    """
    import requests as _rq
    from fastapi.responses import Response

    gw = os.environ.get(
        "MONSTRUO_GATEWAY_URL", "http://monstruo-dev-gateway:9001"
    ).rstrip("/")
    try:
        r = _rq.get(f"{gw}/shared/{asset_path}", timeout=6)
    except Exception:
        return Response(status_code=502)
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type"),
        headers={"Cache-Control": "no-cache"},
    )


app.include_router(rutas_scanner.router_api)

app.include_router(rutas_scanner.router_interno)
app.include_router(rutas_gerencia.router)
app.include_router(rutas_terreno.router)


app.include_router(rutas_supervisor.router)
app.include_router(rutas_health.router)
app.include_router(rutas_ia.router)
app.include_router(rutas_reportes.router)
app.include_router(rutas_auth.router)


# Health Checks (Monitoreo)
@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "terreneitor"}


@app.get("/ready")
async def readiness_check():
    return {"status": "ready"}


# Mount Static Files (AFTER routers to avoid shadowing)
static_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "ui")
)
if os.path.exists(static_dir):
    # html=True hace que un GET a /modulos/<x>/ devuelva su index.html
    # automaticamente. Como esto va DESPUES de los routers/redirects, no
    # captura rutas de la API.
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    log.warning(f"WARNING: Static dir not found at {static_dir}")


# Migracion Automatica
# SECRET-01 (auditoría 2026-06-28): se quitaron las contraseñas hardcodeadas.
# El seeding solo corre si la tabla User está vacía (DB nueva). La contraseña
# se toma de TERRENEITOR_SEED_PASSWORD; si no está, se genera una aleatoria por
# usuario (hay que resetearla). NUNCA volver a poner contraseñas en este código.
SEED_USERS = {
    "juan.lopez@telconsulting.cl": {"name": "Juan Lopez", "role": "GERENCIA"},
    "diego@telconsulting.cl": {"name": "Diego Quintana", "role": "GERENCIA"},
    "nicolas.cerda@telconsulting.cl": {"name": "Nicolas Cerda", "role": "GERENCIA"},
    "francisco.flores@telconsulting.cl": {"name": "Francisco Flores", "role": "SUPERVISOR"},
    "matias.sandoval@telconsulting.cl": {"name": "Matias Sandoval", "role": "TERRENO"},
    "luis.bosch@telconsulting.cl": {"name": "Luis Bosch", "role": "TERRENO"},
}


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            import os as _os
            import secrets as _secrets

            _seed_pass = _os.environ.get("TERRENEITOR_SEED_PASSWORD")
            for email, data in SEED_USERS.items():
                try:
                    _pwd = _seed_pass or _secrets.token_urlsafe(16)
                    if not _seed_pass:
                        log.warning(
                            "[SEED] %s sembrado con password ALEATORIO; resetealo "
                            "(define TERRENEITOR_SEED_PASSWORD para controlarlo)",
                            email,
                        )
                    db.add(
                        User(
                            email=email.lower(),
                            name=data["name"],
                            role=UserRoleEnum(data["role"]),
                            hashed_password=get_db_hash(_pwd),
                        )
                    )
                except Exception:
                    pass
            db.commit()
    finally:
        db.close()
    try:
        db = SessionLocal()
        rutas_admin.sync_projects_db(db, apply_changes=True, log_prefix="[SYNC]")
    except Exception as e:
        log.error(f"[SYNC] error al sincronizar proyectos: {e}")
    finally:
        db.close()
    rutas_admin.start_project_sync_timer()
