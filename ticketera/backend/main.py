from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Inyectar el directorio actual en sys.path para que router/service sean locales.
sys.path.append(str(Path(__file__).parent))

from plataforma.core.env_loader import load_runtime_env

load_runtime_env(Path(__file__).resolve())

from plataforma.core import auth_service, db, deps, jobs_engine, security
from plataforma.core.config import settings as app_settings
from plataforma.core.middleware import AuthIdentityMiddleware
from plataforma.core.web import build_login_redirect_url
from .jobs import ticket_sla, email_jobs
from . import router as tks_router
from . import service as ticketera_service

ROOT_PATH = os.getenv("ROOT_PATH", "").strip()
_WEAK_SECRET_MARKERS = {
    "",
    "CAMBIAME_ESTO_ES_INSEGURO_F8A9",
    "replace_me",
    "dev_only_change_me",
}


def _resolve_shared_ui_dir() -> Optional[Path]:
    repo_root = Path(__file__).resolve().parents[1]
    shared_ui_dir = repo_root / "gateway" / "shared" / "ui"
    return shared_ui_dir if shared_ui_dir.exists() else None


def _html_response(file_path: Path, request: Request) -> HTMLResponse:
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"UI not found: {file_path.name}")
    return HTMLResponse(content=file_path.read_text(encoding="utf-8"))


def _is_weak_secret(secret_key: str) -> bool:
    normalized = str(secret_key or "").strip()
    return normalized in _WEAK_SECRET_MARKERS or len(normalized) < 32


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
    prefix = (request.headers.get("x-forwarded-prefix") or ROOT_PATH).strip().rstrip("/")
    if prefix == "/dev":
        return "/dev"
    return "/"


def _is_request_https(request: Request) -> bool:
    forwarded_proto = (
        request.headers.get("x-forwarded-proto")
        or request.headers.get("x-forwarded-protocol")
        or ""
    )
    forwarded_proto = forwarded_proto.split(",", 1)[0].strip().lower()
    if forwarded_proto:
        return forwarded_proto == "https"

    forwarded_ssl = (request.headers.get("x-forwarded-ssl") or "").strip().lower()
    if forwarded_ssl in ("on", "1", "true", "yes", "y", "si"):
        return True

    return (request.url.scheme or "").strip().lower() == "https"


def _is_cookie_secure_enabled(request: Request) -> bool:
    configured = os.getenv("COOKIE_SECURE", "").strip().lower() in (
        "1",
        "true",
        "t",
        "yes",
        "y",
        "si",
    )
    if not configured:
        return False
    return _is_request_https(request)


def _get_effective_allowed_modules(sess: Dict[str, any]) -> List[str]:
    """
    Calcula la lista de módulos de UI permitidos para un usuario.
    Usa la lógica centralizada de core.auth_service.
    """
    username = sess["username"]
    print(f"[AUTH] Centralized calculation for {username}")
    return auth_service.get_effective_allowed_modules(
        username, 
        sess.get("roles") or []
    )


def _change_password(username: str, old_password: str, new_password: str) -> None:
    if len(str(new_password or "")) < 8:
        raise ValueError("La nueva contraseña debe tener al menos 8 caracteres.")

    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            raise ValueError("Usuario no encontrado.")
        current_hash = str(row.get("password_hash") or "")
        if not security.verify_password(old_password, current_hash):
            raise ValueError("La contraseña actual no coincide.")

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (security.get_password_hash(new_password), username),
        )
        conn.commit()
    finally:
        conn.close()


def _register_ticketera_jobs() -> None:
    jobs_engine.register_job("CHECK_TICKET_SLA", ticket_sla.check_ticket_sla)
    jobs_engine.register_job("TKS_SLA_EVALUATE", ticket_sla.evaluate_ticket_sla_job)
    jobs_engine.register_job(
        "PROCESS_NOTIFICATIONS",
        ticketera_service.process_pending_notifications,
    )
    jobs_engine.register_job("EMAIL_POLLING", email_jobs.poll_email_job)
    jobs_engine.register_job("SEND_AUTO_RESPONSE", email_jobs.send_auto_response_job)
    jobs_engine.register_job("AUTO_CLOSE_TICKETS", email_jobs.auto_close_tickets_job)


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


class PaymentLinkIn(BaseModel):
    customer_id: str
    amount: float


app = FastAPI(
    title="Monstruo - Ticketera API",
    version="1.1",
    root_path=ROOT_PATH,
)
app.add_middleware(AuthIdentityMiddleware)

ui_dir = Path(__file__).parent.parent / "frontend"
shared_ui_dir = _resolve_shared_ui_dir()
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="ticketera_static")
if shared_ui_dir:
    app.mount("/shared", StaticFiles(directory=str(shared_ui_dir)), name="shared_static")

app.include_router(tks_router.router)
app.include_router(tks_router.legacy_router)


@app.on_event("startup")
async def startup() -> None:
    env_type = str(getattr(app_settings, "ENV_TYPE", "dev") or "dev").strip().lower()
    if _is_weak_secret(getattr(app_settings, "SECRET_KEY", "")):
        if env_type == "prod":
            raise RuntimeError("CRITICAL: SECRET_KEY inseguro en PROD.")
        app_settings.SECRET_KEY = secrets.token_urlsafe(64)
        print("[SECURITY] WARN: SECRET_KEY inseguro/ausente. Se generó una clave efímera.")

    db.init_db()
    _register_ticketera_jobs()

    stale_minutes = int(getattr(app_settings, "JOBS_STALE_RUNNING_MINUTES", 20) or 20)
    retention_days = int(getattr(app_settings, "SYS_JOBS_RETENTION_DAYS", 14) or 14)
    recovered = jobs_engine.recover_stale_running_jobs(stale_minutes=stale_minutes)
    cleaned = jobs_engine.cleanup_old_jobs(retention_days=retention_days)

    await jobs_engine.enqueue_unique_job(
        "CHECK_TICKET_SLA",
        payload={"recurring": True},
        max_retries=1,
    )
    await jobs_engine.enqueue_unique_job(
        "TKS_SLA_EVALUATE",
        payload={
            "recurring": True,
            "limit": int(getattr(app_settings, "TKS_SLA_EVAL_LIMIT", 500) or 500),
        },
        max_retries=1,
    )
    await jobs_engine.enqueue_unique_job(
        "EMAIL_POLLING",
        payload={"recurring": True},
        max_retries=0,
    )
    await jobs_engine.enqueue_unique_job(
        "PROCESS_NOTIFICATIONS",
        payload={"recurring": True},
        max_retries=0,
    )
    await jobs_engine.enqueue_unique_job(
        "AUTO_CLOSE_TICKETS",
        payload={"recurring": True},
        max_retries=0,
    )
    await jobs_engine.enqueue_unique_job(
        "RECOVER_STALE_JOBS",
        payload={"recurring": True, "stale_minutes": stale_minutes},
        max_retries=1,
    )
    await jobs_engine.enqueue_unique_job(
        "CLEANUP_SYS_JOBS",
        payload={"recurring": True, "retention_days": retention_days},
        max_retries=1,
    )

    worker_task = getattr(app.state, "job_worker_task", None)
    if worker_task is None or worker_task.done():
        app.state.job_worker_task = asyncio.create_task(jobs_engine.worker_loop())

    print(
        f"[Ticketera Startup] jobs scheduled | recovered_stale={recovered.get('recovered', 0)} "
        f"| cleaned={cleaned.get('deleted', 0)}"
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    worker_task = getattr(app.state, "job_worker_task", None)
    if worker_task and not worker_task.done():
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


@app.get("/", response_class=HTMLResponse)
async def get_index(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
):
    try:
        deps.require_session_hybrid(authorization, access_token)
    except Exception:
        return RedirectResponse(build_login_redirect_url(request, root_path=ROOT_PATH), status_code=302)
    return _html_response(ui_dir / "tks.html", request)


@app.get("/login.html", response_class=HTMLResponse)
async def get_login(request: Request):
    return RedirectResponse(build_login_redirect_url(request, root_path=ROOT_PATH), status_code=302)


@app.get("/health")
async def health():
    return {"status": "ok", "module": "ticketera"}


@app.post("/api/auth/login")
def auth_login(req: LoginRequest, response: Response, request: Request):
    user_data = auth_service.authenticate_user(req.email, req.password)
    if not user_data:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    token = security.create_access_token(
        user_data["username"],
        user_data["role"],
        roles=user_data.get("roles"),
    )
    cookie_domain = _resolve_cookie_domain(request)
    cookie_path = _resolve_cookie_path(request)

    response.delete_cookie("access_token", path=cookie_path)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=720 * 60,
        samesite="lax",
        secure=_is_cookie_secure_enabled(request),
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
def auth_whoami(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return {"logged": False}

    token = token[7:].strip() if token.startswith("Bearer ") else token.strip()
    payload = security.verify_token(token)
    if not payload:
        return {"logged": False}
    roles = payload.get("roles") if isinstance(payload.get("roles"), list) else []
    primary_role = str(payload.get("role") or "").strip().lower()
    if primary_role and primary_role not in roles:
        roles.insert(0, primary_role)
    return {
        "logged": True,
        "email": payload.get("sub"),
        "role": primary_role,
        "roles": roles or ([primary_role] if primary_role else []),
        "user_id": payload.get("sub"),
        "name": payload.get("sub"),
    }


@app.post("/api/auth/logout")
@app.post("/auth/logout")
def auth_logout(response: Response, request: Request):
    cookie_domain = _resolve_cookie_domain(request)
    cookie_path = _resolve_cookie_path(request)
    response.delete_cookie("access_token", path=cookie_path)
    if cookie_domain:
        response.delete_cookie("access_token", domain=cookie_domain, path=cookie_path)
    if cookie_path != "/":
        response.delete_cookie("access_token", path="/")
        if cookie_domain:
            response.delete_cookie("access_token", domain=cookie_domain, path="/")
    return {"ok": True}


@app.get("/api/sesion")
def check_session_status(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
):
    try:
        sess = deps.require_session_hybrid(authorization, access_token)
        return {
            "ok": True,
            "user": sess["username"],
            "role": sess["role"],
            "roles": sess.get("roles") or [sess["role"]],
            "allowed_modules": _get_effective_allowed_modules(sess),
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}


@app.post("/api/auth/change-password")
@app.post("/auth/change-password")
def change_password(
    payload: ChangePasswordIn,
    sess: dict = Depends(deps.require_session_hybrid),
):
    try:
        _change_password(
            sess["username"],
            payload.old_password,
            payload.new_password,
        )
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/jobs/recover-stale")
async def recover_stale_jobs(
    stale_minutes: int = 20,
    sess: dict = Depends(deps.require_permission("tickets:compliance")),
):
    try:
        recovered = jobs_engine.recover_stale_running_jobs(stale_minutes=stale_minutes)
        return {"ok": True, "recovered": recovered}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cobranza/payment-link")
async def generate_payment_link(
    payload: PaymentLinkIn,
    sess: dict = Depends(deps.require_permission("tickets:read")),
):
    customer_id = str(payload.customer_id or "").strip()
    if not customer_id or payload.amount <= 0:
        raise HTTPException(status_code=400, detail="customer_id y amount válidos son requeridos")

    token = secrets.token_urlsafe(24)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    return {
        "payment_url": f"https://pagos.monstruo.cl/pay/{token}?cid={customer_id}&amt={payload.amount:.0f}",
        "token": token,
        "expires_at": expires_at,
    }
