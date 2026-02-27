from typing import Optional, List, Any, Dict
from pathlib import Path
from fastapi import FastAPI, Request, Response, Cookie
from fastapi import Query, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from pydantic import BaseModel
import subprocess
import os
import asyncio
import json
import time
import secrets
from threading import Lock
from dotenv import load_dotenv
from urllib.parse import unquote, urlencode
import httpx

# Cargar .env desde /srv/monstruo/.env (dos niveles arriba de cerebro.py si esta en code/sistema_gestion)
# Path actual de cerebro.py: /srv/monstruo/code/sistema_gestion/cerebro.py
# .env path: /srv/monstruo/.env
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)
from app.core import db, security, auth_service, audit, jobs_engine
from app.core.config import settings as app_settings
from app.api.routers import bancos
from app.jobs import (
    ticket_sla,
    crm_sync,
    stock_sync,
    invoice_sync,
    services_sync,
    compliance_jobs,
    jira_parallel_jobs,
)
from app.procesos import facturacion_job
from app.core import deps as auth_deps
from app.core.middleware import AuthIdentityMiddleware

from app.api.routers import ia as rutas_ia
from app.api.routers import zabbix as rutas_zabbix
from app.api.routers import audit_router as rutas_audit
from app.api.routers import jobs as rutas_jobs
from app.api.routers import tks as rutas_tks
from app.api.routers import bodega as rutas_bodega
from app.api.routers import sales as rutas_sales
from app.api.routers import crm as rutas_crm
from app.api.routers import ops as rutas_ops
from app.api.routers import pmo as rutas_pmo
from app.api.routers import templates as rutas_templates

# --- CONFIGURACION DE PUERTO (9000 por defecto) ---
PORT = int(os.environ.get("PORT", 9000))

app = FastAPI(title="Monstruo API", version="2.0")

_LOGIN_RATE_LOCK = Lock()
_LOGIN_FAILS: Dict[str, List[float]] = {}
_WEAK_SECRET_MARKERS = {
    "",
    "CAMBIAME_ESTO_ES_INSEGURO_F8A9",
    "replace_me",
    "dev_only_change_me",
}

SUBDOMAIN_MAP = {
    "login": "/modulos/login/login.html",
    "erp": "/modulos/erp/erp.html",
    "pmo": "/modulos/pmo/pmo.html",
    "crm": "/modulos/crm/crm.html",
    "bodega": "/modulos/bodega/bodega.html",
    "ticketera": "/modulos/tks/tks.html",
    "ia": "/modulos/ultron/ultron.html",
    "zabbix": "/modulos/zabbix/zabbix.html",
    "config": "/modulos/configuracion/configuracion.html",
}

# --- STATIC FILES ---
static_dir = Path(__file__).resolve().parents[1] / "static"
if not static_dir.exists():
    print(f"WARNING: Static dir not found at {static_dir}")
    # Force absolute for Docker as fallback
    if os.path.exists("/app/code/static"):
        static_dir = Path("/app/code/static")



app.add_middleware(AuthIdentityMiddleware)


def _resolve_cookie_domain(request: Request) -> Optional[str]:
    configured_domain = os.getenv("COOKIE_DOMAIN", "").strip()
    if not configured_domain:
        return None

    request_host = (request.url.hostname or "").strip().lower()
    base_domain = configured_domain.lstrip(".").lower()
    if request_host == base_domain or request_host.endswith("." + base_domain):
        return configured_domain
    return None


def _resolve_cookie_path(request: Request) -> str:
    """Isolate cookie scope for /dev and /prod when behind reverse proxy."""
    prefix = (request.headers.get("x-forwarded-prefix") or "").strip().rstrip("/")
    if prefix in ("/dev", "/prod"):
        return prefix
    return "/"


def _is_cookie_secure_enabled() -> bool:
    return os.getenv("COOKIE_SECURE", "").strip().lower() in (
        "1",
        "true",
        "t",
        "yes",
        "y",
        "si",
    )


def _is_env_flag_enabled(env_var_name: str, default: bool = False) -> bool:
    raw = os.getenv(env_var_name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "t", "yes", "y", "on", "si")


def _is_env_flag_enabled(env_var_name: str, default: bool = False) -> bool:
    raw = os.getenv(env_var_name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "t", "yes", "y", "on", "si")


def _normalize_roles_claim(primary_role: Any, secondary_roles_raw: Any = None) -> List[str]:
    primary = str(primary_role or "").strip().lower()
    roles: List[str] = []

    secondary_source = secondary_roles_raw
    if isinstance(secondary_source, str):
        text = secondary_source.strip()
        if text:
            try:
                secondary_source = json.loads(text)
            except Exception:
                secondary_source = [token.strip() for token in text.split(",") if token.strip()]
        else:
            secondary_source = []

    if isinstance(secondary_source, list):
        for item in secondary_source:
            parsed = str(item or "").strip().lower()
            if parsed and parsed not in roles:
                roles.append(parsed)

    if primary and primary not in roles:
        roles.insert(0, primary)
    return roles or ([primary] if primary else [])


def _is_weak_secret(secret_key: str) -> bool:
    normalized = str(secret_key or "").strip()
    if normalized in _WEAK_SECRET_MARKERS:
        return True
    return len(normalized) < 32


def _login_window_seconds() -> int:
    raw = int(getattr(app_settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300) or 300)
    return max(60, min(3600, raw))


def _login_max_attempts() -> int:
    raw = int(getattr(app_settings, "LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 10) or 10)
    return max(3, min(100, raw))


def _login_throttle_key(request: Request, username: str) -> str:
    ip = (request.client.host if request.client else "unknown").strip().lower()
    user = str(username or "").strip().lower()
    return f"{ip}|{user}"


def _record_login_failure(key: str) -> None:
    now = time.time()
    window = _login_window_seconds()
    with _LOGIN_RATE_LOCK:
        failures = [ts for ts in _LOGIN_FAILS.get(key, []) if (now - ts) < window]
        failures.append(now)
        _LOGIN_FAILS[key] = failures


def _clear_login_failures(key: str) -> None:
    with _LOGIN_RATE_LOCK:
        _LOGIN_FAILS.pop(key, None)


def _login_retry_after_seconds(key: str) -> int:
    now = time.time()
    window = _login_window_seconds()
    max_attempts = _login_max_attempts()
    with _LOGIN_RATE_LOCK:
        failures = [ts for ts in _LOGIN_FAILS.get(key, []) if (now - ts) < window]
        _LOGIN_FAILS[key] = failures
        if len(failures) < max_attempts:
            return 0
        oldest = failures[0]
    retry_after = int(window - (now - oldest))
    return max(1, retry_after)


def _parse_email_allowlist(raw_value: Any) -> set[str]:
    out: set[str] = set()
    for token in str(raw_value or "").split(","):
        email = token.strip().lower()
        if email and "@" in email:
            out.add(email)
    return out


# --- JOB REGISTRY ---
def register_all_jobs():
    # Enlazar string 'SYNC_STOCK' con la función real
    jobs_engine.register_job("SYNC_STOCK", stock_sync.sync_stock)
    jobs_engine.register_job("CHECK_TICKET_SLA", ticket_sla.check_ticket_sla)
    jobs_engine.register_job("TKS_SLA_EVALUATE", ticket_sla.evaluate_ticket_sla_job)
    jobs_engine.register_job("SYNC_CUSTOMERS", crm_sync.sync_customers)
    jobs_engine.register_job("SYNC_BILLING_CYCLES", facturacion_job.run_billing_cycles)
    jobs_engine.register_job("SYNC_INVOICE_PAYMENTS", invoice_sync.sync_invoice_payments)
    jobs_engine.register_job("SYNC_SERVICES_LAUDUS", services_sync.sync_services_from_laudus)
    jobs_engine.register_job("COMPLIANCE_EXPORT_DAILY", compliance_jobs.compliance_export_daily)
    jobs_engine.register_job("COMPLIANCE_PURGE_DAILY", compliance_jobs.compliance_purge_daily)
    jobs_engine.register_job("JIRA_DELTA_SYNC_DAILY", jira_parallel_jobs.jira_delta_sync_daily)

    # Nuevos Jobs de Integración (EPIC 11)
    from app.workers import integrations_worker
    jobs_engine.register_job("WHATSAPP_NOTIFY", integrations_worker.send_whatsapp_notification)
    jobs_engine.register_job("3CX_CALL", integrations_worker.send_3cx_call)
    
    from app.core import tickets_service
    jobs_engine.register_job("PROCESS_NOTIFICATIONS", tickets_service.process_pending_notifications)


@app.on_event("startup")
async def start_background_workers():
    env_type = str(getattr(app_settings, "ENV_TYPE", "dev") or "dev").strip().lower()
    if _is_weak_secret(getattr(app_settings, "SECRET_KEY", "")):
        if env_type == "prod":
            raise RuntimeError("CRITICAL: SECRET_KEY inseguro en PROD. Configura uno largo y aleatorio.")
        generated = secrets.token_urlsafe(64)
        app_settings.SECRET_KEY = generated
        print("[SECURITY] WARN: SECRET_KEY inseguro/ausente. Se generó una clave efímera para este runtime.")

    # 0. Initialize DB
    db.init_db()

    # 1. Registrar trabajos conocidos
    register_all_jobs()

    # 2. Recuperar jobs huérfanos RUNNING + limpieza inicial de históricos.
    stale_minutes = int(getattr(app_settings, "JOBS_STALE_RUNNING_MINUTES", 20) or 20)
    recovered = jobs_engine.recover_stale_running_jobs(stale_minutes=stale_minutes)
    retention_days = int(getattr(app_settings, "SYS_JOBS_RETENTION_DAYS", 14) or 14)
    cleaned = jobs_engine.cleanup_old_jobs(retention_days=retention_days)

    # 3. Asegurar una sola instancia pendiente por job recurrente.
    await jobs_engine.enqueue_unique_job(
        "CHECK_TICKET_SLA", payload={"recurring": True}, max_retries=1
    )
    await jobs_engine.enqueue_unique_job(
        "TKS_SLA_EVALUATE",
        payload={"recurring": True, "limit": int(getattr(app_settings, "TKS_SLA_EVAL_LIMIT", 500) or 500)},
        max_retries=1,
    )
    await jobs_engine.enqueue_unique_job(
        "SYNC_BILLING_CYCLES", payload={"recurring": True}, max_retries=1
    )
    await jobs_engine.enqueue_unique_job(
        "SYNC_INVOICE_PAYMENTS", payload={"recurring": True}, max_retries=1
    )
    await jobs_engine.enqueue_unique_job(
        "SYNC_SERVICES_LAUDUS", payload={"recurring": True}, max_retries=1
    )
    await jobs_engine.enqueue_unique_job(
        "EMAIL_POLLING", payload={"recurring": True}, max_retries=0
    )
    await jobs_engine.enqueue_unique_job(
        "PROCESS_NOTIFICATIONS", payload={"recurring": True}, max_retries=0
    )
    await jobs_engine.enqueue_unique_job(
        "COMPLIANCE_EXPORT_DAILY", payload={"recurring": True}, max_retries=1
    )
    await jobs_engine.enqueue_unique_job(
        "COMPLIANCE_PURGE_DAILY", payload={"recurring": True}, max_retries=1
    )
    await jobs_engine.enqueue_unique_job(
        "JIRA_DELTA_SYNC_DAILY", payload={"recurring": True}, max_retries=1
    )
    await jobs_engine.enqueue_unique_job(
        "CLEANUP_SYS_JOBS",
        payload={"recurring": True, "retention_days": retention_days},
        max_retries=1,
    )

    # 4. Iniciar el Worker Loop (corre en background)
    asyncio.create_task(jobs_engine.worker_loop())

    print(
        f"[Startup] jobs scheduled | recovered_stale={recovered.get('recovered', 0)} "
        f"| cleaned={cleaned.get('deleted', 0)}"
    )




# Routers
app.include_router(rutas_ia.router) # AI / Ultron
app.include_router(rutas_zabbix.router)
app.include_router(rutas_audit.router)
app.include_router(rutas_jobs.router)
app.include_router(rutas_tks.router)
app.include_router(rutas_bodega.router)
app.include_router(rutas_sales.router)
app.include_router(rutas_crm.router)
app.include_router(rutas_ops.router)
app.include_router(rutas_pmo.router)
app.include_router(rutas_templates.router)

# Optional Routers
try:
    from app.api.routers import workflow as rutas_workflow
    app.include_router(rutas_workflow.router)
except ImportError:
    pass

try:
    from app.api.routers import bridge_router as rutas_bridge
    app.include_router(rutas_bridge.router)
except ImportError:
    pass

try:
    from app.api.routers import datos as rutas_datos
    app.include_router(rutas_datos.router)
except ImportError:
    pass

try:
    from app.api.routers import integraciones as rutas_integraciones
    app.include_router(rutas_integraciones.router)
except ImportError:
    pass

try:
    from app.api.routers import conciliacion as rutas_conciliacion
    app.include_router(rutas_conciliacion.router)
except ImportError:
    pass

try:
    from app.api.routers import catalogo as rutas_catalogo
    app.include_router(rutas_catalogo.router)
except ImportError:
    pass

if _is_env_flag_enabled("ADMIN_CHAT_ENABLED", default=False):
    try:
        from app.api.routers import admin_chat as rutas_admin_chat
        app.include_router(rutas_admin_chat.router)
    except ImportError:
        pass

try:
    from app.api.routers import cobranza as rutas_cobranza
    app.include_router(rutas_cobranza.router)
except ImportError:
    pass

try:
    from app.api.routers import config_router as rutas_config
    app.include_router(rutas_config.router)
except ImportError:
    pass

try:
    from app.api.routers import admin_users as rutas_admin_users
    app.include_router(rutas_admin_users.router)
except ImportError:
    pass

try:
    from app.api.routers import bancos as rutas_bancos
    app.include_router(rutas_bancos.router)
except ImportError:
    pass

try:
    from app.api.routers import facturacion as rutas_facturacion
    app.include_router(rutas_facturacion.router)
except ImportError:
    pass


def _serve_module_html(module_path: str, fallback_path: str = "/modulos/login/login.html"):
    file_path = static_dir / module_path.lstrip("/")
    if file_path.exists():
        html = file_path.read_text(encoding="utf-8")
        module_dir = module_path.rsplit("/", 1)[0] + "/"
        base_tag = f'<base href="{module_dir}">'
        if "<base " not in html:
            if "<head>" in html:
                html = html.replace("<head>", f"<head>\n    {base_tag}", 1)
            else:
                html = base_tag + html
        return HTMLResponse(content=html)

    fallback = static_dir / fallback_path.lstrip("/")
    if fallback.exists():
        html = fallback.read_text(encoding="utf-8")
        base_tag = '<base href="/modulos/login/">'
        if "<base " not in html:
            if "<head>" in html:
                html = html.replace("<head>", f"<head>\n    {base_tag}", 1)
            else:
                html = base_tag + html
        return HTMLResponse(content=html)

    raise HTTPException(status_code=404, detail="module_not_found")


@app.get("/health")
def health():
    return {"status": "ok", "app": "monstruo"}


class LoginIn(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def auth_login_compat(req: LoginRequest, response: Response, request: Request):
    throttle_key = _login_throttle_key(request, req.email)
    retry_after = _login_retry_after_seconds(throttle_key)
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos de login. Intenta nuevamente en unos minutos.",
            headers={"Retry-After": str(retry_after)},
        )

    ip = request.client.host if request.client else "unknown"
    user_data = auth_service.authenticate_user(req.email, req.password)
    if not user_data:
        _record_login_failure(throttle_key)
        audit.log_audit(
            req.email,
            "LOGIN_FAILED",
            ip=ip,
            metadata={"scope": "compat", "reason": "bad_credentials"},
        )
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    _clear_login_failures(throttle_key)
    audit.log_audit(
        user_data["username"],
        "LOGIN_SUCCESS",
        ip=ip,
        metadata={"scope": "compat", "role": user_data["role"]},
    )

    token = security.create_access_token(
        user_data["username"],
        user_data["role"],
        roles=user_data.get("roles"),
    )
    configured_domain = os.getenv("COOKIE_DOMAIN", "").strip() or None
    cookie_domain = _resolve_cookie_domain(request)
    cookie_path = _resolve_cookie_path(request)

    response.delete_cookie("access_token", path=cookie_path)
    if configured_domain:
        response.delete_cookie("access_token", domain=configured_domain, path=cookie_path)

    # CRITICAL FIX: Always try to delete root cookie to avoid collisions with /dev or /prod
    if cookie_path != "/":
        response.delete_cookie("access_token", path="/")
        if configured_domain:
            response.delete_cookie("access_token", domain=configured_domain, path="/")

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=720 * 60,
        samesite="lax",
        secure=_is_cookie_secure_enabled(),
        domain=cookie_domain,
        path=cookie_path,
    )

    return {
        "ok": True,
        "role": user_data["role"],
        "roles": user_data.get("roles") or [user_data["role"]],
        "name": user_data["username"],
        "token": token,
    }


@app.get("/api/auth/whoami")
def auth_whoami_compat(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return {"logged": False}

    token = unquote(token)
    if token.startswith("Bearer "):
        token = token[7:]

    payload = security.verify_token(token)
    if not payload:
        return {"logged": False}
    roles = _normalize_roles_claim(payload.get("role"), payload.get("roles"))
    role = roles[0] if roles else str(payload.get("role") or "").strip().lower()

    return {
        "logged": True,
        "email": payload["sub"],
        "role": role,
        "roles": roles,
        "user_id": payload["sub"],
        "name": payload["sub"],
    }


@app.post("/api/auth/logout")
@app.post("/auth/logout")
def auth_logout_compat(response: Response, request: Request):
    configured_domain = os.getenv("COOKIE_DOMAIN", "").strip() or None
    cookie_domain = _resolve_cookie_domain(request)
    cookie_path = _resolve_cookie_path(request)

    # In prefixed mode (/dev or /prod), avoid emitting root-path delete cookie,
    # otherwise proxy path rewriting can generate duplicated paths (e.g. /devdev).
    if cookie_path == "/":
        response.delete_cookie("access_token")
        if cookie_domain:
            response.delete_cookie("access_token", domain=cookie_domain)
        if configured_domain and configured_domain != cookie_domain:
            response.delete_cookie("access_token", domain=configured_domain)

    response.delete_cookie("access_token", path=cookie_path)
    if cookie_domain:
        response.delete_cookie("access_token", domain=cookie_domain, path=cookie_path)
    if configured_domain and configured_domain != cookie_domain:
        response.delete_cookie("access_token", domain=configured_domain, path=cookie_path)

    return {"ok": True}


@app.get("/api/sesion")
def check_session_status(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
):
    try:
        sess = auth_deps.require_session_hybrid(authorization, access_token)
        
        # Fetch allowed_modules from DB
        allowed = []
        conn = db.get_conn()
        try:
            # Use %s for psycopg (Postgres)
            row = conn.execute("SELECT allowed_modules FROM users WHERE username=%s", (sess["username"],)).fetchone()
            if row and row["allowed_modules"]:
                import json
                try:
                    allowed = json.loads(row["allowed_modules"])
                except:
                    allowed = []
        except Exception as e:
            print(f"Error fetching allowed_modules: {e}")
        finally:
            conn.close()

        return {
            "ok": True, 
            "user": sess["username"], 
            "role": sess["role"],
            "roles": sess.get("roles") or [sess["role"]],
            "allowed_modules": allowed
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}


@app.get("/api/auth/google/login")
async def google_login(request: Request):
    # Detectar el prefijo para la URI de redirección
    prefix = request.headers.get("X-Forwarded-Prefix", "")
    if prefix:
        redirect_uri = f"https://login.telconsulting.cl{prefix}/api/auth/google/callback"
    else:
        redirect_uri = f"{str(request.base_url).rstrip('/')}/api/auth/google/callback"

    oauth_state = secrets.token_urlsafe(32)
    state_ttl = max(120, min(3600, int(getattr(app_settings, "GOOGLE_OAUTH_STATE_TTL_SECONDS", 600) or 600)))

    params = {
        "client_id": app_settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": oauth_state,
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    login_response = RedirectResponse(url)
    login_response.set_cookie(
        key="oauth_state",
        value=oauth_state,
        httponly=True,
        max_age=state_ttl,
        samesite="lax",
        secure=_is_cookie_secure_enabled(),
        domain=_resolve_cookie_domain(request),
        path=_resolve_cookie_path(request),
    )
    return login_response


@app.get("/api/auth/google/callback")
async def google_callback(request: Request, code: str, state: str):
    expected_state = str(request.cookies.get("oauth_state") or "").strip()
    if not expected_state or not state or not secrets.compare_digest(str(state).strip(), expected_state):
        raise HTTPException(status_code=400, detail="invalid_oauth_state")

    prefix = request.headers.get("X-Forwarded-Prefix", "")
    if prefix:
        redirect_uri = f"https://login.telconsulting.cl{prefix}/api/auth/google/callback"
    else:
        redirect_uri = f"{str(request.base_url).rstrip('/')}/api/auth/google/callback"

    # Intercambiar código por token
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": app_settings.GOOGLE_CLIENT_ID,
                "client_secret": app_settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        )
        token_data = token_res.json()
        if "access_token" not in token_data:
            raise HTTPException(status_code=400, detail=f"Failed to get token: {token_data}")

        # Obtener info del usuario
        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        )
        user_info = user_res.json()
        email = user_info.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Failed to get email from Google")

    # Verificar si el usuario existe en nuestra DB o auto-crear solo si está explícitamente autorizado.
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT username, role, secondary_roles, is_active FROM users WHERE username=?", (email,)).fetchone()
        if not row:
            email_lc = str(email or "").strip().lower()
            role_map = {
                "juan.lopez@telconsulting.cl": "admin",
                "diego@telconsulting.cl": "gerencia",
                "fabian.correa@telconsulting.cl": "encargado_mesa",
            }
            auto_allowlist = _parse_email_allowlist(getattr(app_settings, "GOOGLE_AUTO_PROVISION_ALLOWLIST", ""))
            can_auto_provision = email_lc in role_map or email_lc in auto_allowlist
            if not can_auto_provision:
                raise HTTPException(status_code=403, detail="Usuario no autorizado para auto-provisión")

            role = role_map.get(email_lc, "ops")
            auth_service.create_user(email, os.urandom(24).hex(), role)
            row = {"username": email, "role": role, "secondary_roles": "[]", "is_active": 1}
        
        if int(row["is_active"] or 0) != 1:
            raise HTTPException(status_code=403, detail="Usuario inactivo")

        user_data = {
            "username": row["username"],
            "role": str(row["role"] or "").strip().lower(),
            "roles": _normalize_roles_claim(row.get("role"), row.get("secondary_roles")),
        }
    finally:
        conn.close()

    # Generar sesión
    token = security.create_access_token(
        user_data["username"],
        user_data["role"],
        roles=user_data.get("roles"),
    )
    
    # Redirigir al dashboard con la cookie seteada
    target = f"{prefix}/dashboard" if prefix else "/dashboard"
    final_response = RedirectResponse(url=target)
    
    cookie_path = prefix if prefix else "/"
    configured_domain = os.environ.get("COOKIE_DOMAIN")
    cookie_domain = _resolve_cookie_domain(request)

    # Limpieza de cookies de raíz para evitar colisiones
    if cookie_path != "/":
        final_response.delete_cookie("access_token", path="/")
        final_response.delete_cookie("oauth_state", path="/")
        if configured_domain:
            final_response.delete_cookie("access_token", domain=configured_domain, path="/")
            final_response.delete_cookie("oauth_state", domain=configured_domain, path="/")

    final_response.delete_cookie("oauth_state", path=cookie_path)
    if configured_domain:
        final_response.delete_cookie("oauth_state", domain=configured_domain, path=cookie_path)

    final_response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=720 * 60,
        samesite="lax",
        secure=_is_cookie_secure_enabled(),
        domain=cookie_domain,
        path=cookie_path,
    )
    
    return final_response


@app.post("/auth/login")
def login(body: LoginIn, request: Request):
    throttle_key = _login_throttle_key(request, body.username)
    retry_after = _login_retry_after_seconds(throttle_key)
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="too_many_login_attempts",
            headers={"Retry-After": str(retry_after)},
        )

    ip = request.client.host if request.client else "unknown"
    user_data = auth_service.authenticate_user(body.username, body.password)
    if not user_data:
        _record_login_failure(throttle_key)
        audit.log_audit(
            body.username,
            "LOGIN_FAILED",
            ip=ip,
            metadata={"scope": "v1", "reason": "bad_credentials"},
        )
        raise HTTPException(status_code=401, detail="bad_credentials")

    _clear_login_failures(throttle_key)
    audit.log_audit(
        user_data["username"],
        "LOGIN_SUCCESS",
        ip=ip,
        metadata={"scope": "v1", "role": user_data["role"]},
    )
    token = security.create_access_token(
        user_data["username"],
        user_data["role"],
        roles=user_data.get("roles"),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user_data["role"],
        "roles": user_data.get("roles") or [user_data["role"]],
    }


@app.get("/auth/me")
def me(authorization: Optional[str] = Header(default=None)):
    user = auth_deps.require_session(authorization)
    return {"username": user["username"], "role": user["role"], "roles": user.get("roles") or [user["role"]]}


@app.get("/dashboard")
def dashboard_root(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
):
    try:
        auth_deps.require_session_hybrid(authorization, access_token)
    except Exception:
        # Usar X-Forwarded-Prefix inyectado por Nginx para saber si es /prod o /dev
        prefix = request.headers.get("x-forwarded-prefix", "/prod")
        login_url = f"https://login.telconsulting.cl{prefix}/"
        return RedirectResponse(login_url, status_code=302)

    return _serve_module_html("/modulos/dashboard/dashboard.html")


@app.get("/")
def read_root(request: Request):
    host = request.headers.get("host", "").split(":")[0]
    subdomain = host.split(".")[0] if "." in host else ""

    module_path = SUBDOMAIN_MAP.get(subdomain, SUBDOMAIN_MAP["login"])
    return _serve_module_html(module_path)

# --- STATIC FILES --- (Managed at the top)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
