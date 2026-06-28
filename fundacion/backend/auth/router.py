"""Login PROPIO de Fundación — independiente del gateway de Monstruo.

Separación fase 2. Endpoints:
  POST /api/auth/login            correo + contraseña -> cookie access_token (JWT)
  GET  /api/auth/whoami           estado de sesión (lee la cookie)
  POST /api/auth/logout           borra la cookie
  POST /api/auth/change-password  cambia la contraseña del usuario en sesión
  GET  /api/sesion                sesión + allowed_modules + fundacion_scope (lo usa la UI)

Autentica contra fundacion.users (no auth.users). Firma el JWT con el SECRET_KEY
de la config de Fundación (en fase 4 será una llave propia, distinta de Monstruo).
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from pydantic import BaseModel

from fundacion.core import db, deps, security
from fundacion.core import auth_service
from fundacion.core.config import settings

router = APIRouter()


# ── Modelos ──────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


# ── Helpers de cookie (replicados del gateway, adaptados) ────────────────
def _resolve_cookie_domain(request: Request) -> Optional[str]:
    configured = os.getenv("COOKIE_DOMAIN", "").strip()
    if not configured:
        return None
    host = (request.url.hostname or "").strip().lower()
    base = configured.lstrip(".").lower()
    if host == base or host.endswith("." + base):
        return configured
    return None


def _resolve_cookie_path(request: Request) -> str:
    prefix = (request.headers.get("x-forwarded-prefix") or "").strip().rstrip("/")
    return "/dev" if prefix == "/dev" else "/"


def _is_request_https(request: Request) -> bool:
    proto = (
        request.headers.get("x-forwarded-proto")
        or request.headers.get("x-forwarded-protocol")
        or ""
    ).split(",", 1)[0].strip().lower()
    if proto:
        return proto == "https"
    if (request.headers.get("x-forwarded-ssl") or "").strip().lower() in ("on", "1", "true", "yes", "y", "si"):
        return True
    return (request.url.scheme or "").strip().lower() == "https"


def _is_cookie_secure_enabled(request: Request) -> bool:
    if os.getenv("COOKIE_SECURE", "").strip().lower() not in ("1", "true", "t", "yes", "y", "si"):
        return False
    return _is_request_https(request)


# ── Rate-limit de login en memoria (anti fuerza bruta, sin Redis) ────────
_login_fail_log: dict = defaultdict(list)


def _rl_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "?"
    return f"{ip}|{(email or '').strip().lower()}"


def _rl_blocked(key: str) -> bool:
    now = time.time()
    window = getattr(settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300)
    maxa = getattr(settings, "LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 10)
    _login_fail_log[key] = [t for t in _login_fail_log[key] if now - t < window]
    return len(_login_fail_log[key]) >= maxa


# ── change-password contra fundacion.users ───────────────────────────────
def _change_password(username: str, old_password: str, new_password: str) -> None:
    if len(str(new_password or "")) < 8:
        raise ValueError("La nueva contraseña debe tener al menos 8 caracteres.")
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT password_hash FROM fundacion.users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            raise ValueError("Usuario no encontrado.")
        if not security.verify_password(old_password, str(row.get("password_hash") or "")):
            raise ValueError("La contraseña actual no coincide.")
        conn.execute(
            "UPDATE fundacion.users SET password_hash = ? WHERE username = ?",
            (security.get_password_hash(new_password), username),
        )
        conn.commit()
    finally:
        conn.close()


# ── Endpoints ────────────────────────────────────────────────────────────
@router.post("/api/auth/login")
def auth_login(req: LoginRequest, response: Response, request: Request):
    key = _rl_key(request, req.email)
    if _rl_blocked(key):
        raise HTTPException(status_code=429, detail="Demasiados intentos fallidos. Espera unos minutos.")

    user = auth_service.authenticate_user(req.email, req.password)
    if not user:
        _login_fail_log[key].append(time.time())
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    _login_fail_log.pop(key, None)

    token = security.create_access_token(user["username"], user["role"], roles=user.get("roles"))
    cookie_domain = _resolve_cookie_domain(request)
    cookie_path = _resolve_cookie_path(request)
    for _p in ("/", "/dev"):
        response.delete_cookie("access_token", path=_p)
        if cookie_domain:
            response.delete_cookie("access_token", domain=cookie_domain, path=_p)
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
        "role": user["role"],
        "roles": user.get("roles") or [user["role"]],
        "name": user["username"],
        "token": token,
    }


@router.get("/api/auth/whoami")
def auth_whoami(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return {"logged": False}
    token = token[7:].strip() if token.startswith("Bearer ") else token.strip()
    payload = security.verify_token(token)
    if not payload:
        return {"logged": False}
    roles = payload.get("roles") if isinstance(payload.get("roles"), list) else []
    primary = str(payload.get("role") or "").strip().lower()
    if primary and primary not in roles:
        roles.insert(0, primary)
    return {
        "logged": True,
        "email": payload.get("sub"),
        "role": primary,
        "roles": roles or ([primary] if primary else []),
        "user_id": payload.get("sub"),
        "name": payload.get("sub"),
    }


@router.post("/api/auth/logout")
@router.post("/auth/logout")
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


@router.post("/api/auth/change-password")
@router.post("/auth/change-password")
def change_password(
    payload: ChangePasswordIn,
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
):
    sess = deps.require_session_hybrid(authorization, access_token)
    try:
        _change_password(sess["username"], payload.old_password, payload.new_password)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/sesion")
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
            "allowed_modules": auth_service.get_effective_allowed_modules(
                sess["username"], sess.get("roles") or []
            ),
            "fundacion_scope": auth_service.get_user_fundacion_scope(sess["username"]),
            "display_name": auth_service.get_user_display_name(sess["username"]),
        }
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}
