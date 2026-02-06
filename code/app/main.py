from typing import Optional, List, Any, Dict
from pathlib import Path
from fastapi import FastAPI, Request, Response, Cookie
from fastapi import Query, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
import subprocess
import os
import asyncio
from dotenv import load_dotenv

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
from app.api.routers import pmo as rutas_pmo
from app.api.routers import templates as rutas_templates

# --- CONFIGURACION DE PUERTO (9000 por defecto) ---
PORT = int(os.environ.get("PORT", 9000))

app = FastAPI(title="Monstruo API", version="2.0")

app.add_middleware(AuthIdentityMiddleware)


# --- JOB REGISTRY ---
def register_all_jobs():
    # Enlazar string 'SYNC_STOCK' con la función real
    jobs_engine.register_job("SYNC_STOCK", stock_sync.sync_stock)
    jobs_engine.register_job("CHECK_TICKET_SLA", ticket_sla.check_ticket_sla)
    jobs_engine.register_job("SYNC_CUSTOMERS", crm_sync.sync_customers)
    jobs_engine.register_job("SYNC_BILLING_CYCLES", facturacion_job.run_billing_cycles)
    jobs_engine.register_job("SYNC_INVOICE_PAYMENTS", invoice_sync.sync_invoice_payments)
    jobs_engine.register_job("SYNC_SERVICES_LAUDUS", services_sync.sync_services_from_laudus)


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
    print(f"[Startup] Billing and SLA jobs scheduled")


# Routers ULTRON (IA) y Zabbix
app.include_router(rutas_ia.router)
app.include_router(rutas_zabbix.router)
app.include_router(rutas_audit.router)
app.include_router(rutas_jobs.router)
app.include_router(rutas_tks.router)
app.include_router(rutas_bodega.router)
app.include_router(rutas_sales.router)
app.include_router(rutas_crm.router)
app.include_router(rutas_ops.router)
app.include_router(rutas_pmo.router)
app.include_router(rutas_pmo.router)
app.include_router(rutas_templates.router)
# --- STATIC FILES (Root mount for Neon Command UX) ---
static_dir = Path(__file__).resolve().parents[1] / "static"
if not static_dir.exists():
    print(f"WARNING: Static dir not found at {static_dir}")


@app.get("/")
def read_root():
    return RedirectResponse("/modulos/login/login.html")


@app.get("/login.html")
def login_redirect():
    return RedirectResponse("/modulos/login/login.html")


@app.get("/inicio.html")
def inicio_redirect():
    return RedirectResponse("/modulos/dashboard/inicio.html")


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok", "app": "monstruo"}


class LoginIn(BaseModel):
    username: str
    password: str


# Mount static files at root / (must be last or handle 404 carefully, but FastAPI handles specific routes first)
# We mount specific files/dirs or catch-all only if no other route matches.
# Best practice: Mount static at "/" but keep API routes prioritized.
# Moving this typically to the END of the file is safer if using a catch-all,
# but StaticFiles works well if routes are defined before it.
# However, to be safe with all API routes, we should enable it,
# but keep in mind that "html=True" allows serving index.html if present.
# We'll attach it later in the file if possible, or trust FastAPI order (routes first).
# Actually, let's keep it here but note that dynamic routes defined LATER might be shadowed
# if the static handler matches everything.
# Better pattern: Define specific API routes FIRST.
# For now, we will define it at the END of the file or rely on FastAPI 0.60+ behavior.
# Let's verify existing route structure.
# We'll just define the mount logic here but actually CALL mount at the end?
# No, let's just mount it here.


# --- COMPATIBILITY LAYER (Terreneitor Frontend Support) ---
# El frontend de Terreneitor (login.js) espera:
# POST /api/auth/login with JSON {email, password}
# GET /api/auth/whoami


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def auth_login_compat(req: LoginRequest, response: Response, request: Request):
    ip = request.client.host if request.client else "unknown"

    # Map email to username for Monstruo
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

    # Create JWT
    token = security.create_access_token(user_data["username"], user_data["role"])

    # Terreneitor expects cookie 'access_token'
    # Format: "Bearer <token>"
    token_val = f"Bearer {token}"
    cookie_domain = os.getenv("COOKIE_DOMAIN", "").strip() or None
    cookie_secure = os.getenv("COOKIE_SECURE", "").strip().lower() in (
        "1",
        "true",
        "t",
        "yes",
        "y",
        "si",
    )
    response.set_cookie(
        key="access_token",
        value=token_val,
        httponly=True,
        max_age=720 * 60,
        samesite="lax",
        secure=cookie_secure,
        domain=cookie_domain,
    )

    # Return JSON expected by login.js
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

    # Parse Bearer
    if token.startswith("Bearer "):
        token = token[7:]

    # Verify JWT
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
def auth_logout_compat(response: Response):
    cookie_domain = os.getenv("COOKIE_DOMAIN", "").strip() or None
    response.delete_cookie("access_token", domain=cookie_domain)
    return {"ok": True}


@app.get("/api/sesion")
def check_session_status(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
):
    try:
        sess = auth_deps.require_session_hybrid(authorization, access_token)
        return {"ok": True, "user": sess["username"], "role": sess["role"]}
    except:
        return {"ok": False, "detail": "No autenticado"}


# --- END COMPATIBILITY LAYER ---


# Original Monstruo Auth (kept for backward compat or valid API usage)
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


# -----------------------------
# ACTIONS (protected)
# -----------------------------
@app.post("/actions/sync-now")
def sync_now(sess: dict = Depends(auth_deps.require_permission("invoice:sync"))):
    # Permission 'invoice:sync' required (admin/ops)

    p = subprocess.run(["python3", "run_pipeline.py"], capture_output=True, text=True)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={"step_failed": True, "stdout": out[-1500:], "stderr": err[-1500:]},
        )
    return {"status": "ok", "stdout": out[-2000:]}


# -----------------------------
# Alerts endpoints (protected read)
# -----------------------------
@app.get("/alerts")
def list_alerts(
    sess: dict = Depends(auth_deps.require_permission("dashboard:read")),
    status: str = Query("open", pattern="^(open|resolved|all)$"),
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    # Permission 'dashboard:read' (admin/ops/finance)

    db.init_db()
    conn = db.get_conn()
    try:
        where = []
        params: List[Any] = []
        if status != "all":
            where.append("status = ?")
            params.append(status)
        if severity:
            where.append("severity = ?")
            params.append(severity)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
            SELECT rule, severity, entity_type, entity_id, summary, status, first_seen_at, last_seen_at, resolved_at, occurrences
            FROM alerts
            {where_sql}
            ORDER BY last_seen_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = conn.execute(sql, tuple(params)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/alerts/summary")
def alerts_summary(
    sess: dict = Depends(auth_deps.require_permission("dashboard:read")),
):

    db.init_db()
    conn = db.get_conn()
    try:
        sev = conn.execute("""
            SELECT severity, count(*) AS n
            FROM alerts
            WHERE status='open'
            GROUP BY severity
            ORDER BY n DESC
        """).fetchall()
        rule = conn.execute("""
            SELECT rule, count(*) AS n
            FROM alerts
            WHERE status='open'
            GROUP BY rule
            ORDER BY n DESC
        """).fetchall()
        return {
            "by_severity": {r["severity"]: r["n"] for r in sev},
            "by_rule": {r["rule"]: r["n"] for r in rule},
        }
    finally:
        conn.close()


try:
    from app.api.routers import workflow as rutas_workflow

    app.include_router(rutas_workflow.router)
except Exception:
    pass

try:
    from app.api.routers.crm import router as crm_router

    app.include_router(crm_router)
except Exception:
    pass

# from summary_api import router as summary_router

# app.include_router(summary_router)

# from compliance_api import router as compliance_router

# app.include_router(compliance_router)

# from events_api import router as events_router

# app.include_router(events_router)

from app.api.routers import ai as rutas_ai

app.include_router(rutas_ai.router)

from app.api.routers.bridge import router as bridge_router

app.include_router(bridge_router)

try:
    from app.api.routers.datos import router as datos_router

    app.include_router(datos_router)
except ImportError:
    print("Warning: rutas_datos not found")

from app.api.routers import integraciones as rutas_integraciones

app.include_router(rutas_integraciones.router)

from app.api.routers import conciliacion as rutas_conciliacion

app.include_router(rutas_conciliacion.router)

from app.api.routers import tks as rutas_tks

app.include_router(rutas_tks.router)

from app.api.routers import catalogo as rutas_catalogo

app.include_router(rutas_catalogo.router)

from app.api.routers import bodega as rutas_bodega

app.include_router(rutas_bodega.router)

from app.api.routers import ultron as rutas_ultron

app.include_router(rutas_ultron.router)

from app.api.routers import admin_chat as rutas_admin_chat

app.include_router(rutas_admin_chat.router)

from app.api.routers import cobranza as rutas_cobranza

app.include_router(rutas_cobranza.router)

from app.api.routers import config as rutas_config

app.include_router(rutas_config.router)

from app.api.routers import bancos as rutas_bancos

app.include_router(rutas_bancos.router)

from app.api.routers import facturacion as rutas_facturacion

app.include_router(rutas_facturacion.router)

app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
