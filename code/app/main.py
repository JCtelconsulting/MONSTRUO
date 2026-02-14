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
from dotenv import load_dotenv
from urllib.parse import unquote

# Cargar .env desde /srv/monstruo/.env (dos niveles arriba de cerebro.py si esta en code/sistema_gestion)
# Path actual de cerebro.py: /srv/monstruo/code/sistema_gestion/cerebro.py
# .env path: /srv/monstruo/.env
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)
from app.core import db, security, auth_service, audit, jobs_engine
from app.api.routers import bancos
from app.jobs import ticket_sla, crm_sync, stock_sync, invoice_sync, services_sync
from app.procesos import facturacion_job
from app.core import deps as auth_deps
from app.core.middleware import AuthIdentityMiddleware

from app.api.routers import ia as rutas_ia
from app.api.routers import zabbix as rutas_zabbix
from app.api.routers import audit as rutas_audit
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

SUBDOMAIN_MAP = {
    "login": "/modulos/login/login.html",
    "erp": "/modulos/erp/erp.html",
    "pmo": "/modulos/pmo/dashboard.html",
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


# --- JOB REGISTRY ---
def register_all_jobs():
    # Enlazar string 'SYNC_STOCK' con la función real
    jobs_engine.register_job("SYNC_STOCK", stock_sync.sync_stock)
    jobs_engine.register_job("CHECK_TICKET_SLA", ticket_sla.check_ticket_sla)
    jobs_engine.register_job("SYNC_CUSTOMERS", crm_sync.sync_customers)
    jobs_engine.register_job("SYNC_BILLING_CYCLES", facturacion_job.run_billing_cycles)
    jobs_engine.register_job("SYNC_INVOICE_PAYMENTS", invoice_sync.sync_invoice_payments)
    jobs_engine.register_job("SYNC_SERVICES_LAUDUS", services_sync.sync_services_from_laudus)

    # Nuevos Jobs de Integración (EPIC 11)
    from app.workers import integrations_worker
    jobs_engine.register_job("WHATSAPP_NOTIFY", integrations_worker.send_whatsapp_notification)
    jobs_engine.register_job("3CX_CALL", integrations_worker.send_3cx_call)
    
    from app.core import tickets_service
    jobs_engine.register_job("PROCESS_NOTIFICATIONS", tickets_service.process_pending_notifications)


@app.on_event("startup")
async def start_background_workers():
    # 0. Initialize DB
    db.init_db()

    # 1. Registrar trabajos conocidos
    register_all_jobs()

    # 2. Iniciar el Worker Loop (corre en background)
    asyncio.create_task(jobs_engine.worker_loop())

    # 3. Encolar job recurrente de SLA (cada 30 minutos)
    from datetime import datetime, timedelta

    now_dt = datetime.utcnow()
    next_run = (now_dt + timedelta(minutes=30)).isoformat()
    await jobs_engine.enqueue_job(
        "CHECK_TICKET_SLA", payload={"recurring": True}, max_retries=1
    )
    # Encolar ciclo de facturación (cada 12 horas)
    await jobs_engine.enqueue_job(
        "SYNC_BILLING_CYCLES", payload={"recurring": True}, max_retries=1
    )
    # Encolar sync de pagos de facturas (cada 6 horas)
    await jobs_engine.enqueue_job(
        "SYNC_INVOICE_PAYMENTS", payload={"recurring": True}, max_retries=1
    )
    # Encolar sync de servicios desde Laudus (diario)
    await jobs_engine.enqueue_job(
        "SYNC_SERVICES_LAUDUS", payload={"recurring": True}, max_retries=1
    )
    # Encolar ciclo de lectura de correos (inicia inmediatamente, luego se re-agenda)
    await jobs_engine.enqueue_job(
        "EMAIL_POLLING", payload={}, max_retries=0
    )
    
    # Job para procesar notificaciones escalonadas (polling cada 1 min idealmente)
    # Por ahora lo lanzamos una vez y deberíamos re-agendarlo igual que email polling
    await jobs_engine.enqueue_job(
        "PROCESS_NOTIFICATIONS", payload={"recurring": True}, max_retries=0
    )

    print(f"[Startup] Billing, SLA and Email jobs scheduled")




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
    from app.api.routers import bridge as rutas_bridge
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
    from app.api.routers import config as rutas_config
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
    ip = request.client.host if request.client else "unknown"
    user_data = auth_service.authenticate_user(req.email, req.password)
    if not user_data:
        audit.log_audit(
            req.email,
            "LOGIN_FAILED",
            ip=ip,
            metadata={"scope": "compat", "reason": "bad_credentials"},
        )
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    audit.log_audit(
        user_data["username"],
        "LOGIN_SUCCESS",
        ip=ip,
        metadata={"scope": "compat", "role": user_data["role"]},
    )

    token = security.create_access_token(user_data["username"], user_data["role"])
    configured_domain = os.getenv("COOKIE_DOMAIN", "").strip() or None
    cookie_domain = _resolve_cookie_domain(request)
    cookie_path = _resolve_cookie_path(request)

    response.delete_cookie("access_token", path=cookie_path)
    if configured_domain:
        response.delete_cookie("access_token", domain=configured_domain, path=cookie_path)

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

    return {
        "logged": True,
        "email": payload["sub"],
        "role": payload["role"],
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
            "allowed_modules": allowed
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}


@app.post("/auth/login")
def login(body: LoginIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    user_data = auth_service.authenticate_user(body.username, body.password)
    if not user_data:
        audit.log_audit(
            body.username,
            "LOGIN_FAILED",
            ip=ip,
            metadata={"scope": "v1", "reason": "bad_credentials"},
        )
        raise HTTPException(status_code=401, detail="bad_credentials")

    audit.log_audit(
        user_data["username"],
        "LOGIN_SUCCESS",
        ip=ip,
        metadata={"scope": "v1", "role": user_data["role"]},
    )
    token = security.create_access_token(user_data["username"], user_data["role"])
    return {"access_token": token, "token_type": "bearer", "role": user_data["role"]}


@app.get("/auth/me")
def me(authorization: Optional[str] = Header(default=None)):
    user = auth_deps.require_session(authorization)
    return {"username": user["username"], "role": user["role"]}


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
