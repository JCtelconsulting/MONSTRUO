from __future__ import annotations

import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlsplit

import httpx

from plataforma.core.env_loader import load_runtime_env

load_runtime_env(Path(__file__).resolve())
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response as FastAPIResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from gateway.backend.routers import admin_users, config_router, gta_areas, ops
from plataforma.core import auth_service, db, deps, security
from plataforma.core.config import settings as app_settings
from plataforma.core.middleware import AuthIdentityMiddleware
from plataforma.core.version import inject_asset_version
from plataforma.core.web import build_login_redirect_url

ROOT_PATH = os.getenv("ROOT_PATH", "").strip()
_WEAK_SECRET_MARKERS = {
    "",
    "CAMBIAME_ESTO_ES_INSEGURO_F8A9",
    "replace_me",
    "dev_only_change_me",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    env_type = str(getattr(app_settings, "ENV_TYPE", "dev") or "dev").strip().lower()
    if _is_weak_secret(getattr(app_settings, "SECRET_KEY", "")):
        if env_type == "prod":
            raise RuntimeError("CRITICAL: SECRET_KEY inseguro en PROD.")
        app_settings.SECRET_KEY = secrets.token_urlsafe(64)
        logger.warning("[SECURITY] SECRET_KEY inseguro/ausente. Se generó una clave efímera.")
    db.init_db()
    yield


app = FastAPI(
    title="Monstruo OS - Gateway Perimetral",
    version="4.0",
    root_path=ROOT_PATH,
    lifespan=lifespan,
)
app.add_middleware(AuthIdentityMiddleware)

ui_dir = Path(__file__).parent.parent / "ui"
repo_root = Path(__file__).resolve().parents[2]
fundacion_ui_dir = repo_root / "fundacion" / "ui"
gta_ui_dir = repo_root / "gta" / "ui"


def _public_prefix(request: Request) -> str:
    prefix = (request.headers.get("x-forwarded-prefix") or ROOT_PATH).strip().rstrip("/")
    return prefix


def _request_subdomain(request: Request) -> str:
    host = (request.headers.get("host") or request.url.hostname or "").split(":")[0].strip().lower()
    return host.split(".")[0] if "." in host else ""

def _service_root_url(request: Request, prod_host: str, local_port: int) -> str:
    if (request.url.hostname or "").endswith(".telconsulting.cl"):
        return f"https://{prod_host}.telconsulting.cl{_public_prefix(request)}/"
    protocol = request.url.scheme or "http"
    host = request.url.hostname or "127.0.0.1"
    return f"{protocol}://{host}:{local_port}/"


def _serve_module_html(request: Request, module_path: str, fallback_path: str = "/login/login.html") -> HTMLResponse:
    search_roots: List[Path] = [ui_dir]

    relative_module_path = module_path.lstrip("/")
    for root in search_roots:
        file_path = root / relative_module_path
        if not file_path.exists():
            continue

        html = file_path.read_text(encoding="utf-8")
        module_dir = module_path.rsplit("/", 1)[0] + "/"
        prefix = _public_prefix(request)
        base_href = f"{prefix}/{module_dir}".replace("//", "/") if prefix else module_dir
        if not base_href.endswith("/"):
            base_href += "/"
        base_tag = f'<base href="{base_href}">'
        
        # Siempre reescribimos el <base href> existente o lo inyectamos
        import re
        if re.search(r'<base\s+href="[^"]*">', html):
            html = re.sub(r'<base\s+href="[^"]*">', base_tag, html)
        elif "<head>" in html:
            html = html.replace("<head>", f"<head>\n    {base_tag}", 1)
        else:
            html = base_tag + html
        return HTMLResponse(content=inject_asset_version(html))

    fallback_relative_path = fallback_path.lstrip("/")
    for root in search_roots:
        fallback_file = root / fallback_relative_path
        if not fallback_file.exists():
            continue

        html = fallback_file.read_text(encoding="utf-8")
        fallback_dir = fallback_path.rsplit("/", 1)[0] + "/"
        prefix = _public_prefix(request)
        base_href = f"{prefix}/{fallback_dir}".replace("//", "/") if prefix else fallback_dir
        if not base_href.endswith("/"):
            base_href += "/"
        base_tag = f'<base href="{base_href}">'
        
        # Siempre reescribimos el <base href> existente o lo inyectamos
        import re
        if re.search(r'<base\s+href="[^"]*">', html):
            html = re.sub(r'<base\s+href="[^"]*">', base_tag, html)
        elif "<head>" in html:
            html = html.replace("<head>", f"<head>\n    {base_tag}", 1)
        else:
            html = base_tag + html
        return HTMLResponse(content=inject_asset_version(html))

    raise HTTPException(status_code=404, detail="module_not_found")


def _serve_static_file(base_dir: Path, asset_path: str) -> FileResponse:
    root_dir = base_dir.resolve()
    file_path = (root_dir / asset_path).resolve()
    try:
        file_path.relative_to(root_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="asset_not_found") from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="asset_not_found")
    return FileResponse(file_path)


def _prefixed_path(request: Request, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    prefix = _public_prefix(request)
    return f"{prefix}{normalized_path}" if prefix else normalized_path


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
    return auth_service.get_effective_allowed_modules(
        sess["username"], 
        sess.get("roles") or []
    )


def _change_password(username: str, old_password: str, new_password: str) -> None:
    if len(str(new_password or "")) < 8:
        raise ValueError("La nueva contrasena debe tener al menos 8 caracteres.")

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
            raise ValueError("La contrasena actual no coincide.")

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (security.get_password_hash(new_password), username),
        )
        conn.commit()
    finally:
        conn.close()


def _root_redirect_target(request: Request) -> str:
    subdomain = _request_subdomain(request)
    if subdomain == "config":
        return "configuracion/configuracion.html"
    if subdomain == "login":
        return "login/login.html"
    return "dashboard/dashboard.html"


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str

app.include_router(admin_users.router)
app.include_router(config_router.router)
app.include_router(gta_areas.router)
app.include_router(ops.router)

SERVICES_MAP = {
    "ticketera": f"http://ticketera:{os.getenv('TICKETERA_PORT', '9005')}",
    "tks":       f"http://ticketera:{os.getenv('TICKETERA_PORT', '9005')}",
    "fundacion": f"http://fundacion:{os.getenv('FUNDACION_PORT', '9006')}",
    "bodega":    f"http://bodega:{os.getenv('BODEGA_PORT', '9007')}",
    "crm":       f"http://crm:{os.getenv('CRM_PORT', '9008')}",
    "erp":       f"http://erp:{os.getenv('ERP_PORT', '9009')}",
    "pmo":       f"http://pmo:{os.getenv('PMO_PORT', '9010')}",
    "ia":        f"http://ia:{os.getenv('IA_PORT', '9011')}",
    "gta":       f"http://gta:{os.getenv('GTA_PORT', '9012')}",
    "zabbix":    f"http://zabbix:{os.getenv('ZABBIX_PORT', '9013')}",
    "terreneitor": f"http://terreneitor:{os.getenv('TERRENEITOR_PORT', '8005')}",
}

SERVICE_API_PREFIX = {
    "ticketera": "tks",
    "tks": "tks",
    "erp": None,
    "bodega": None,
    "crm": None,
    "pmo": "pmo",
    "ia": "ultron",
    "zabbix": "zabbix",
    "fundacion": "fundacion",
    "gta": "gta",
}


async def _proxy_to_target(target_url: str, request: Request) -> FastAPIResponse:
    async with httpx.AsyncClient() as client:
        content = await request.body()
        headers = dict(request.headers)
        original_host = (request.headers.get("host") or request.url.hostname or "").strip()
        if original_host:
            headers["host"] = original_host
            headers["x-forwarded-host"] = original_host

        response = await client.request(
            request.method,
            target_url,
            content=content,
            headers=headers,
            params=request.query_params,
            timeout=30.0,
        )

        passthrough_headers: Dict[str, str] = {}
        for key, value in response.headers.items():
            lowered = key.lower()
            if lowered in {"content-length", "transfer-encoding", "connection", "content-encoding"}:
                continue
            if lowered == "location":
                parsed = urlsplit(value)
                if parsed.scheme and parsed.netloc:
                    netloc = parsed.netloc.split(":")[0].lower()
                    if netloc == "ticketera":
                        suffix = parsed.path or "/"
                        if parsed.query:
                            suffix += f"?{parsed.query}"
                        if parsed.fragment:
                            suffix += f"#{parsed.fragment}"
                        value = suffix
            passthrough_headers[key] = value

        return FastAPIResponse(
            content=response.content,
            status_code=response.status_code,
            headers=passthrough_headers,
            media_type=response.headers.get("content-type"),
        )




@app.post("/api/auth/login")
def auth_login(req: LoginRequest, response: Response, request: Request):
    user_data = auth_service.authenticate_user(req.email, req.password)
    if not user_data:
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    token = security.create_access_token(
        user_data["username"],
        user_data["role"],
        roles=user_data.get("roles"),
    )
    cookie_domain = _resolve_cookie_domain(request)
    cookie_path = _resolve_cookie_path(request)

    # Borrar CUALQUIER access_token previo en ambos paths (/ y /dev) y dominios antes de setear
    # el nuevo. Si no, al loguear en dev queda también el de prod (path=/) y el navegador manda
    # las dos cookies juntas; la sesión se lee de forma ambigua y "a veces no deja entrar a dev
    # hasta pasar por prod". Con un solo access_token vigente desaparece esa intermitencia.
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
            "fundacion_scope": auth_service.get_user_fundacion_scope(sess["username"]),
            "display_name": auth_service.get_user_display_name(sess["username"]),
        }
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def service_proxy(service: str, path: str, request: Request):
    if service not in SERVICES_MAP:
        if _request_subdomain(request) == "ticketera":
            if service == "jobs":
                return await _proxy_to_target(f"{SERVICES_MAP['ticketera']}/api/{service}/{path}", request)
            return await _proxy_to_target(f"{SERVICES_MAP['ticketera']}/api/tks/{service}/{path}", request)
        raise HTTPException(status_code=404, detail="Service not found")

    api_prefix = SERVICE_API_PREFIX.get(service)
    if api_prefix:
        target_url = f"{SERVICES_MAP[service]}/api/{api_prefix}/{path}"
    else:
        target_url = f"{SERVICES_MAP[service]}/api/{path}"
    return await _proxy_to_target(target_url, request)


@app.get("/")
async def root(request: Request):
    if _request_subdomain(request) == "ticketera":
        return await _proxy_to_target(f"{SERVICES_MAP['ticketera']}/", request)
    if _request_subdomain(request) == "login":
        return _serve_module_html(request, "/login/login.html")
    if _request_subdomain(request) == "config":
        return _serve_module_html(request, "/configuracion/configuracion.html")
    return RedirectResponse(url=_root_redirect_target(request))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_root(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
):
    try:
        deps.require_session_hybrid(authorization, access_token)
    except Exception:
        return RedirectResponse(build_login_redirect_url(request, root_path=ROOT_PATH), status_code=302)
    return _serve_module_html(request, "/dashboard/dashboard.html")


@app.get("/dashboard/")
@app.get("/dashboard/dashboard.html")
async def dashboard_canonical_redirect(request: Request):
    return RedirectResponse(_prefixed_path(request, "/dashboard"), status_code=302)


@app.get("/login")
@app.get("/login/")
@app.get("/login/login.html")
async def login_page(request: Request):
    return _serve_module_html(request, "/login/login.html")


@app.get("/configuracion")
@app.get("/configuracion/")
@app.get("/configuracion/configuracion.html")
async def config_page(request: Request):
    try:
        deps.require_session_hybrid(
            request.headers.get("authorization"),
            request.cookies.get("access_token"),
        )
    except Exception:
        return RedirectResponse(build_login_redirect_url(request, root_path=ROOT_PATH), status_code=302)
    return _serve_module_html(request, "/configuracion/configuracion.html")


@app.get("/dashboard/{asset_path:path}")
async def dashboard_static(asset_path: str):
    return _serve_static_file(ui_dir / "dashboard", asset_path)


@app.get("/configuracion/{asset_path:path}")
async def config_static(asset_path: str):
    return _serve_static_file(ui_dir / "configuracion", asset_path)


@app.get("/login/{asset_path:path}")
async def login_static(asset_path: str):
    return _serve_static_file(ui_dir / "login", asset_path)


@app.get("/shared/{asset_path:path}")
async def shared_static(asset_path: str):
    return _serve_static_file(ui_dir / "shared" / "ui", asset_path)


@app.get("/fundacion")
async def fundacion_root(request: Request):
    return RedirectResponse(_prefixed_path(request, "/fundacion/"), status_code=302)


@app.get("/fundacion/")
async def fundacion_root_slash():
    index_path = fundacion_ui_dir / "fundacion.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="fundacion_ui_not_found")
    return HTMLResponse(inject_asset_version(index_path.read_text(encoding="utf-8")))


@app.get("/fundacion/fundacion.html")
async def fundacion_canonical_redirect(request: Request):
    return RedirectResponse(_prefixed_path(request, "/fundacion/"), status_code=302)


@app.get("/gta")
async def gta_root(request: Request):
    return RedirectResponse(_prefixed_path(request, "/gta/"), status_code=302)


@app.get("/gta/")
async def gta_root_slash():
    index_path = gta_ui_dir / "gta.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="gta_ui_not_found")
    return HTMLResponse(inject_asset_version(index_path.read_text(encoding="utf-8")))


@app.get("/gta/gta.html")
async def gta_canonical_redirect(request: Request):
    return RedirectResponse(_prefixed_path(request, "/gta/"), status_code=302)


@app.get("/fundacion/{asset_path:path}")
async def fundacion_static(asset_path: str):
    return _serve_static_file(fundacion_ui_dir, asset_path)


@app.get("/gta/{asset_path:path}")
async def gta_static(asset_path: str):
    if asset_path.startswith("shared/"):
        return _serve_static_file(ui_dir / "shared" / "ui", asset_path[len("shared/"):])
    return _serve_static_file(gta_ui_dir, asset_path)


@app.get("/health")
async def health():
    return {"status": "ok", "gateway": "active"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def ticketera_host_proxy(path: str, request: Request):
    if _request_subdomain(request) != "ticketera":
        raise HTTPException(status_code=404, detail="not_found")

    normalized_path = str(path or "").lstrip("/")
    if normalized_path.startswith(("api/auth/", "api/sesion", "auth/", "shared/")):
        raise HTTPException(status_code=404, detail="not_found")

    if normalized_path.startswith("api/") and not normalized_path.startswith(("api/tks/", "api/jobs/")):
        suffix = f"/api/tks/{normalized_path[4:]}"
    else:
        suffix = f"/{normalized_path}" if normalized_path else "/"
    return await _proxy_to_target(f"{SERVICES_MAP['ticketera']}{suffix}", request)
