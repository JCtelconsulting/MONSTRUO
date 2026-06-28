# ========================= rutas_auth.py (PROD FIX CLEAN) =========================
import os
import secrets
import urllib.parse
from datetime import timedelta

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError
from sqlalchemy.orm import Session

from terreneitor.backend import dependencias, modelos
from terreneitor.backend.utils.logger import log

router = APIRouter(prefix="/api", tags=["Auth"])
COOKIE_DOMAIN = ".telconsulting.cl"


@router.post("/auth/login")
@dependencias.limiter.limit("5/minute")
def auth_login(
    request: Request,
    req: modelos.LoginRequest,
    db: Session = Depends(dependencias.get_db),
):
    email = (req.email or "").strip().lower()
    user = db.query(modelos.User).filter(modelos.User.email == email).first()

    if (not user) or (
        not dependencias.verify_password(req.password, user.hashed_password)
    ):
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    access_token_expires = timedelta(minutes=dependencias.ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = dependencias.create_access_token(
        data={
            "sub": user.email,
            "user_id": user.id,
            "role": user.role.value,
            "name": user.name,
        },
        expires_delta=access_token_expires,
    )

    response = JSONResponse({"ok": True, "role": user.role.value, "name": user.name})
    # Limpiar cookies viejas/duplicadas antes de setear la nueva (evita loops).
    dependencias.clear_cookie(response, request)
    dependencias.set_cookie(response, access_token, request)
    return response


@router.get("/auth/whoami")
def auth_whoami(request: Request, db: Session = Depends(dependencias.get_db)):
    jwt_token = dependencias.get_token_from_cookie(request)
    if jwt_token:
        try:
            payload = dependencias.jwt.decode(
                jwt_token,
                dependencias.SECRET_KEY,
                algorithms=[dependencias.ALGORITHM],
            )
            return {
                "logged": True,
                "email": payload.get("sub"),
                "name": payload.get("name"),
                "role": payload.get("role"),
                "user_id": payload.get("user_id"),
            }
        except JWTError:
            pass
        except Exception:
            pass
    # SSO Monstruo: aceptar la sesión del gateway (cookie access_token)
    try:
        sso = dependencias._session_desde_gateway(request, db)
    except Exception:
        sso = None
    return sso if sso else {"logged": False}


@router.get("/sesion")
def api_sesion(request: Request, db: Session = Depends(dependencias.get_db)):
    """Sesión estilo Monstruo: usuario + módulos permitidos del ecosistema.

    Lo consume la barra del hub para mostrar los módulos Monstruo a los que el
    usuario puede entrar (auth.users.allowed_modules del Postgres compartido).
    """
    info = auth_whoami(request, db)
    if not info.get("logged"):
        return {"ok": False}
    email = (info.get("email") or "").strip().lower()
    allowed = []
    # Paridad canónica: preguntarle al gateway de Monstruo (misma red docker)
    # con la cookie SSO; él calcula los módulos efectivos (override o rol).
    raw_sso = request.cookies.get(dependencias.MONSTRUO_SSO_COOKIE)
    if raw_sso and dependencias.MONSTRUO_SSO_SECRET:
        gw = os.environ.get(
            "MONSTRUO_GATEWAY_URL", "http://monstruo-dev-gateway:9001"
        ).rstrip("/")
        try:
            r = requests.get(
                f"{gw}/api/sesion",
                cookies={dependencias.MONSTRUO_SSO_COOKIE: raw_sso},
                timeout=4,
            )
            if r.ok and r.json().get("ok"):
                allowed = r.json().get("allowed_modules") or []
        except Exception:
            allowed = []
    if allowed:
        return {
            "ok": True,
            "user": email,
            "name": info.get("name"),
            "role": info.get("role"),
            "allowed_modules": allowed,
        }
    try:
        from sqlalchemy import text as _text

        row = db.execute(
            _text(
                "SELECT role, COALESCE(allowed_modules::text, '') "
                "FROM auth.users WHERE lower(username) = :u "
                "AND COALESCE(is_active::int, 0) = 1"
            ),
            {"u": email},
        ).first()
        if row:
            if (row[0] or "").strip().lower() == "admin":
                allowed = ["*"]
            else:
                import json as _json

                try:
                    allowed = [str(m) for m in _json.loads(row[1] or "[]")]
                except Exception:
                    allowed = []
    except Exception:
        allowed = []  # modo standalone (SQLite): sin módulos del ecosistema
    return {
        "ok": True,
        "user": email,
        "name": info.get("name"),
        "role": info.get("role"),
        "allowed_modules": allowed,
    }


@router.post("/auth/logout")
def auth_logout(request: Request):
    response = JSONResponse({"ok": True})
    dependencias.clear_cookie(response, request)
    # SSO Monstruo: borrar también la cookie del gateway (dominio compartido)
    # para que "Salir" cierre la sesión de TODO el ecosistema, no solo de este
    # módulo (el JWT es stateless: sin cookie no hay sesión).
    if dependencias.MONSTRUO_SSO_SECRET:
        for dom in (".telconsulting.cl", None):
            response.delete_cookie(
                dependencias.MONSTRUO_SSO_COOKIE, domain=dom, path="/"
            )
    return response


@router.post("/auth/change-password")
def change_password(
    req: modelos.PasswordChangeRequest,
    user: modelos.User = Depends(dependencias.get_current_user),
    db: Session = Depends(dependencias.get_db),
):
    if not dependencias.verify_password(req.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Clave actual incorrecta")

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Nueva clave muy corta")

    user.hashed_password = dependencias.get_db_hash(req.new_password)
    db.commit()
    return {"status": "ok"}


# --- Google OAuth (Minimal OIDC) ---
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


def _load_simple_env_file(path: str):
    """Carga KEY=VALUE a os.environ si no existen (parser mínimo, sin deps)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k:
                    # No pisar valores ya provistos por el runtime (docker/systemd/etc).
                    if os.environ.get(k) in (None, ""):
                        os.environ[k] = v
    except Exception:
        return


def _try_load_local_dotenv():
    # Carga .env desde el directorio raíz del proyecto actual
    # Esto permite que funcione tanto en /srv/terreneitor como en /srv/terreneitor_dev
    base_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    paths = [
        os.path.join(base_dir, "environments", ".env"),
        os.path.join(base_dir, ".env"),
        os.path.join(base_dir, "code", ".env"),
    ]
    for p in paths:
        if os.path.exists(p):
            _load_simple_env_file(p)


def _detect_env_key(request: Request | None = None) -> str:
    """
    Detecta ambiente para elegir cliente OAuth (dev/prod).

    Orden:
    1) header X-Terreneitor-Env (nginx)
    2) x-forwarded-prefix/root_path (/dev o /prod)
    3) cookie terreneitor_env=dev (legacy)
    4) ENV / TERRENEITOR_ENV
    5) host local (localhost / IP privada)
    """
    try:
        if request is not None:
            hdr = (request.headers.get("x-terreneitor-env") or "").strip().lower()
            if hdr in {"dev", "prod"}:
                return hdr

            prefix = _get_forwarded_prefix(request)
            if prefix == "/dev":
                return "dev"
            if prefix == "/prod":
                return "prod"

            if (request.cookies.get("terreneitor_env") or "").strip().lower() == "dev":
                return "dev"

            host = (
                request.headers.get("x-forwarded-host")
                or request.headers.get("host")
                or ""
            )
            host = host.split(":")[0].strip().lower()
            if host in {"localhost", "127.0.0.1"} or host.startswith(
                ("127.", "10.", "172.", "192.168.")
            ):
                return "dev"
    except Exception:
        pass

    env = (
        ((os.environ.get("ENV") or "") or (os.environ.get("TERRENEITOR_ENV") or ""))
        .strip()
        .lower()
    )
    if env in {"dev", "development"}:
        return "dev"
    if env in {"prod", "production"}:
        return "prod"

    return "prod"


def _get_forwarded_prefix(request: Request) -> str:
    # Respeta reverse proxy (nginx/traefik) si define prefijo (ej: /dev o /prod)
    pref = (
        request.headers.get("x-forwarded-prefix")
        or request.scope.get("root_path")
        or ""
    )
    if not pref:
        return ""
    if not str(pref).startswith("/"):
        pref = "/" + str(pref)
    return str(pref).rstrip("/")


def _get_google_redirect_uri(request: Request) -> str:
    _try_load_local_dotenv()
    env_key = _detect_env_key(request)

    explicit = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI") or os.environ.get(
        "TERRENEITOR_GOOGLE_REDIRECT_URI"
    )
    if explicit:
        return explicit.strip()

    explicit_env = (
        os.environ.get(f"GOOGLE_OAUTH_REDIRECT_URI_{env_key.upper()}")
        or os.environ.get(f"TERRENEITOR_GOOGLE_REDIRECT_URI_{env_key.upper()}")
        or ""
    ).strip()
    if explicit_env:
        return explicit_env

    prefix = _get_forwarded_prefix(request)

    # Detección robusta de esquema y host detrás de proxy
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or "localhost"
    )
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme

    # Forzar https en dominios de producción/dev conocidos
    if ".telconsulting.cl" in host:
        proto = "https"

    # Default: {host}{prefix}/api/auth/google/callback
    return f"{proto}://{host}{prefix}/api/auth/google/callback"


def _get_google_client(request: Request | None = None) -> tuple[str, str]:
    _try_load_local_dotenv()
    env_key = _detect_env_key(request)

    client_id = (
        os.environ.get(f"GOOGLE_OAUTH_CLIENT_ID_{env_key.upper()}")
        or os.environ.get(f"TERRENEITOR_GOOGLE_CLIENT_ID_{env_key.upper()}")
        or os.environ.get(f"GOOGLE_CLIENT_ID_{env_key.upper()}")
        or os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
        or os.environ.get("GOOGLE_CLIENT_ID")
        or os.environ.get("TERRENEITOR_GOOGLE_CLIENT_ID")
        or ""
    ).strip()
    client_secret = (
        os.environ.get(f"GOOGLE_OAUTH_CLIENT_SECRET_{env_key.upper()}")
        or os.environ.get(f"TERRENEITOR_GOOGLE_CLIENT_SECRET_{env_key.upper()}")
        or os.environ.get(f"GOOGLE_CLIENT_SECRET_{env_key.upper()}")
        or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
        or os.environ.get("GOOGLE_CLIENT_SECRET")
        or os.environ.get("TERRENEITOR_GOOGLE_CLIENT_SECRET")
        or ""
    ).strip()
    return client_id, client_secret


def _make_state(next_path: str) -> str:
    # Estado firmado para evitar CSRF; exp corta (5 min)
    return dependencias.create_access_token(
        data={
            "purpose": "google_oauth",
            "next": next_path,
            "nonce": secrets.token_urlsafe(16),
        },
        expires_delta=timedelta(minutes=5),
    )


def _decode_state(state: str) -> dict:
    return dependencias.jwt.decode(
        state, dependencias.SECRET_KEY, algorithms=[dependencias.ALGORITHM]
    )


@router.get("/auth/google/login")
def google_login(request: Request, next: str = "/"):
    client_id, _ = _get_google_client(request)
    if not client_id:
        raise HTTPException(status_code=500, detail="Google OAuth no configurado")

    redirect_uri = _get_google_redirect_uri(request)
    state = _make_state(next)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return RedirectResponse(url=url)


@router.get("/auth/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(dependencias.get_db),
):
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Callback incompleto")

    # Validar state
    try:
        st = _decode_state(state)
        if st.get("purpose") != "google_oauth":
            raise ValueError("bad state")
    except Exception:
        raise HTTPException(status_code=400, detail="State invalido")

    client_id, client_secret = _get_google_client(request)
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth no configurado")

    redirect_uri = _get_google_redirect_uri(request)

    # Intercambiar code por tokens
    try:
        token_resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
    except Exception:
        raise HTTPException(status_code=502, detail="No se pudo contactar Google")

    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Token exchange fallido")

    token_data = token_resp.json() or {}
    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="Respuesta Google invalida")

    # Validar id_token via tokeninfo (evita dependencias extra)
    try:
        info = requests.get(
            GOOGLE_TOKENINFO_URL, params={"id_token": id_token}, timeout=10
        ).json()
    except Exception:
        raise HTTPException(status_code=502, detail="No se pudo validar token")

    aud = info.get("aud")
    if isinstance(aud, list):
        ok_aud = client_id in aud
    else:
        ok_aud = aud == client_id
    if not ok_aud:
        raise HTTPException(status_code=401, detail="Token invalido")

    email = (info.get("email") or "").strip().lower()
    name = (info.get("name") or "").strip() or email
    if not email:
        raise HTTPException(status_code=400, detail="Google no entrego email")

    user = db.query(modelos.User).filter(modelos.User.email == email).first()
    if not user:
        # Por seguridad: no auto-provision en este fix.
        raise HTTPException(status_code=403, detail="Usuario no autorizado")

    access_token_expires = timedelta(minutes=dependencias.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = dependencias.create_access_token(
        data={
            "sub": user.email,
            "user_id": user.id,
            "role": user.role.value,
            "name": user.name or name,
        },
        expires_delta=access_token_expires,
    )

    # Redirección final por rol + entorno (subdominios)
    prefix = _get_forwarded_prefix(request)
    # Detección de entorno:
    # - si venimos por /dev (path prefix), estamos en DEV
    # - si el proxy usa cookie para switchear upstream, también sirve como fallback
    env_key = _detect_env_key(request)

    role = (user.role.value if hasattr(user.role, "value") else str(user.role)).upper()
    dest_by_role = {
        "ADMIN": "portal.telconsulting.cl",
        "GERENCIA": "gerencial.telconsulting.cl",
        "SUPERVISOR": "supervisor.telconsulting.cl",
        "TERRENO": "terreneitor.telconsulting.cl",
    }
    domain = dest_by_role.get(role, "portal.telconsulting.cl")

    # Usar el protocolo detectado antes
    proto = request.headers.get("x-forwarded-proto") or "https"

    # Si el proxy usa prefijo visible (/dev), mantenerlo; si no, URL limpia.
    final_path = "/dev/" if (env_key == "dev" and prefix == "/dev") else "/"
    final_url = f"{proto}://{domain}{final_path}"

    log.info(
        f"[AUTH] Google Login exitoso para {email}. Redirigiendo a {final_url} (env={env_key}, role={role})"
    )

    response = RedirectResponse(url=final_url)
    dependencias.clear_cookie(response, request)
    dependencias.set_cookie(response, access_token, request)
    return response
