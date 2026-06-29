# ========================= dependencias.py (v5.1 - FIX TIME) =========================
# Se agrega 'import time' para compatibilidad y se mantienen las cookies globales.
# =====================================================================================
import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session, sessionmaker

from terreneitor.backend.core.nucleo import SessionLocal, get_engine
from terreneitor.backend.models import modelos

# --- Rate Limiter Compartido ---
limiter = Limiter(key_func=get_remote_address)
_disable_ratelimit = (
    os.environ.get("TERRENEITOR_DISABLE_RATELIMIT", "0") == "1"
    or os.environ.get("ENV") == "test"
    or "PYTEST_CURRENT_TEST" in os.environ
)
if _disable_ratelimit:

    def _no_limit(*args, **kwargs):
        def _decorator(func):
            return func

        return _decorator

    limiter.limit = _no_limit  # type: ignore[attr-defined]


# --- Helpers de entorno ---
def _is_test_env() -> bool:
    return (
        os.environ.get("ENV") == "test"
        or os.environ.get("TERRENEITOR_TEST_MODE") == "1"
        or "PYTEST_CURRENT_TEST" in os.environ
    )


# --- Configuración JWT ---
def _load_shared_secret_from_file() -> str:
    """
    Permite compartir sesión entre prod/dev leyendo la clave canónica.
    """
    env_file = "/etc/terreneitor/terreneitor.env"
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line or line.lstrip().startswith("#"):
                    continue
                if line.startswith("TERRENEITOR_SECRET_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


SECRET_KEY = (
    os.environ.get("TERRENEITOR_SHARED_SECRET_KEY", "").strip()
    or _load_shared_secret_from_file()
    or os.environ.get("TERRENEITOR_SECRET_KEY", "").strip()
)
if not SECRET_KEY:
    raise RuntimeError("Missing TERRENEITOR_SECRET_KEY env var")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

pwd_context = CryptContext(
    schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Funciones Crypto ---


def _pw_bytes_72(s):
    if s is None:
        b = b""
    elif isinstance(s, bytes):
        b = s
    else:
        b = str(s).encode("utf-8", "ignore")
    if len(b) > 72:
        b = b[:72]
    return b


def _hash_bytes(s):
    if s is None:
        return b""
    if isinstance(s, bytes):
        return s
    return str(s).encode("utf-8", "ignore")


def get_db_hash(password: str) -> str:
    pw = _pw_bytes_72(password)
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw, salt).decode("utf-8", "ignore")


def verify_password(plain_password, hashed_password):
    pw = _pw_bytes_72(plain_password)
    hpw = _hash_bytes(hashed_password)
    try:
        return bcrypt.checkpw(pw, hpw)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- Manejo de Cookies ---


def _is_prod_env() -> bool:
    return os.environ.get("ENV", "").lower() in {"prod", "production"}


def _is_dev_env() -> bool:
    return os.environ.get("ENV", "").lower() in {"dev", "development"}


# Nombre de cookie POR ENTORNO: aísla la sesión de dev y prod aunque compartan
# dominio (.telconsulting.cl) y el path /dev. Permite estar logueado en ambos a
# la vez sin que una sesión pise a la otra.
# En PROD NO usar 'access_token': ese nombre es el del gateway sobre .telconsulting.cl
# y se pisarían mutuamente (rompiendo el SSO). La sesión del gateway se lee aparte
# vía MONSTRUO_SSO_COOKIE; la propia de Terreneitor usa un nombre dedicado.
COOKIE_NAME = "access_token_dev" if _is_dev_env() else "access_token_terreneitor"


def _get_cookie_domain() -> str | None:
    """
    Dominio de cookie para compartir sesion entre subdominios en PROD.

    En DEV/local (IP/localhost) NO se debe fijar domain (cookie host-only),
    porque el browser la descarta si el dominio no coincide.
    """
    raw = os.environ.get("TERRENEITOR_DOMAIN")
    if raw is None or raw.strip() == "":
        return ".telconsulting.cl" if _is_prod_env() else None
    raw = raw.strip()
    if raw.lower() in {"none", "null"}:
        return None
    return raw


def _get_cookie_secure_default() -> bool:
    # En prod asumimos HTTPS; en dev/local por defecto NO secure para permitir HTTP.
    return True if _is_prod_env() else False


def set_cookie(response: Response, token: str, request: Request | None = None):
    """Set cookie de sesión.

    En DEV es común servir por HTTP (IP/localhost) o con dominios que no matchean
    TERRENEITOR_DOMAIN. Para evitar "login loop", si detectamos un request no-HTTPS
    o host local, relajamos secure/domain aunque el env venga con valores de PROD.
    """

    # Defaults desde env/config
    secure_cookie = os.environ.get("TERRENEITOR_COOKIE_SECURE")
    if secure_cookie is None or secure_cookie.strip() == "":
        secure = _get_cookie_secure_default()
    else:
        secure = secure_cookie.strip() == "1"

    cookie_domain = _get_cookie_domain()

    # Ajustes por request (solo si no estamos en prod)
    if request is not None and not _is_prod_env() and not _is_test_env():
        xf_proto = (
            (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
        )
        scheme = (xf_proto or request.url.scheme or "").lower()
        host = (request.headers.get("host") or "").split(":")[0].strip().lower()

        is_local_host = (
            host in {"localhost", "127.0.0.1"}
            or host.endswith(".local")
            or host.startswith("127.")
            or host.startswith("192.168.")
            or host.startswith("10.")
            or host.startswith("172.")
        )

        # En DEV, si el host real no calza con el dominio configurado,
        # forzar host-only para evitar que el browser descarte la cookie.
        host_matches_domain = True
        if cookie_domain:
            bare = cookie_domain.lstrip(".").lower()
            host_matches_domain = host == bare or host.endswith("." + bare)

        if scheme != "https" or is_local_host:
            secure = False
        if is_local_host or not host_matches_domain:
            cookie_domain = None

    if _is_test_env():
        secure = False
        cookie_domain = None

    response.set_cookie(
        key=COOKIE_NAME,
        value=f"Bearer {token}",
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=cookie_domain,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def clear_cookie(response: Response, request: Request | None = None):
    cookie_domain = _get_cookie_domain()
    secure_cookie = os.environ.get("TERRENEITOR_COOKIE_SECURE")
    if secure_cookie is None or secure_cookie.strip() == "":
        secure = _get_cookie_secure_default()
    else:
        secure = secure_cookie.strip() == "1"

    if request is not None and not _is_prod_env() and not _is_test_env():
        xf_proto = (
            (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
        )
        scheme = (xf_proto or request.url.scheme or "").lower()
        host = (request.headers.get("host") or "").split(":")[0].strip().lower()
        is_local_host = (
            host in {"localhost", "127.0.0.1"}
            or host.endswith(".local")
            or host.startswith("127.")
            or host.startswith("192.168.")
            or host.startswith("10.")
            or host.startswith("172.")
        )
        host_matches_domain = True
        if cookie_domain:
            bare = cookie_domain.lstrip(".").lower()
            host_matches_domain = host == bare or host.endswith("." + bare)
        if scheme != "https" or is_local_host:
            secure = False
        if is_local_host or not host_matches_domain:
            cookie_domain = None

    if _is_test_env():
        cookie_domain = None
        secure = False

    # Borrar AMBOS nombres (entorno actual + legacy) en todas las variantes de
    # domain — limpia cookies viejas/duplicadas que cruzaban dev/prod.
    domains = {None, cookie_domain}
    env_domain = (os.environ.get("TERRENEITOR_DOMAIN") or "").strip()
    if env_domain and env_domain.lower() not in {"none", "null"}:
        domains.add(env_domain)
    domains.add(".telconsulting.cl")
    for name in {COOKIE_NAME, "access_token"}:
        for dom in domains:
            response.delete_cookie(
                key=name,
                domain=dom,
                path="/",
                httponly=True,
                secure=secure,
                samesite="lax",
            )


# --- Dependencia de Base de Datos ---


def get_db(request: Request = None):
    # Si hay request, determinamos el tenant por el Host
    if request:
        host = request.headers.get("host", "default")
        # Quitamos puerto si existe (ej: localhost:8000)
        host = host.split(":")[0]
        engine = get_engine(host)
        SessionLocalDynamic = sessionmaker(
            autocommit=False, autoflush=False, bind=engine
        )
        db = SessionLocalDynamic()
    else:
        # Fallback para scripts sin request context
        db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# --- Extracción de Token ---
def get_token_from_cookie(request: Request):
    # Tolerante a cookies duplicadas con el mismo nombre (host-only vieja + la
    # nueva con Domain): parsea el header crudo, prueba todos los valores de
    # COOKIE_NAME y devuelve el primero cuyo JWT sea válido.
    raw = request.headers.get("cookie") or ""
    candidates = []
    for part in raw.split(";"):
        part = part.strip()
        if not part.startswith(COOKIE_NAME + "="):
            continue
        val = part[len(COOKIE_NAME) + 1 :].strip().strip('"')
        if val.startswith("Bearer "):
            candidates.append(val.split(" ", 1)[1])
    if not candidates:
        token = request.cookies.get(COOKIE_NAME)
        if token and token.startswith("Bearer "):
            candidates.append(token.split(" ", 1)[1])
    for cand in candidates:
        try:
            jwt.decode(cand, SECRET_KEY, algorithms=[ALGORITHM])
            return cand
        except JWTError:
            continue
    return candidates[0] if candidates else None


# --- SSO Monstruo: aceptar la sesión del gateway (login.telconsulting.cl) ---
# Si está seteado MONSTRUO_SSO_SECRET (la SECRET_KEY del stack Monstruo), un
# usuario logueado en el gateway entra a Terreneitor sin segundo login.
# Autorización: auth.users.allowed_modules debe incluir "terreneitor" (o rol
# admin del gateway). Solo funciona en modo Postgres compartido (schema auth).
MONSTRUO_SSO_SECRET = os.environ.get("MONSTRUO_SSO_SECRET", "").strip()
MONSTRUO_SSO_COOKIE = os.environ.get("MONSTRUO_SSO_COOKIE", "access_token").strip()
MONSTRUO_SSO_ALG = os.environ.get("MONSTRUO_SSO_ALG", "HS256").strip()
# rol del gateway -> rol local
_SSO_ROL_MAP = {
    # ADMIN se fusionó en GERENCIA: la administración se hace desde la config de Monstruo,
    # así que quien era admin/sistemas entra a Terreneitor como GERENCIA (rol administrativo).
    "admin": "GERENCIA",
    "sistemas": "GERENCIA",
    "gerencia": "GERENCIA",
    "supervisor": "SUPERVISOR",
    "supervisor_terreno": "SUPERVISOR",
    "ops": "SUPERVISOR",
    "terreno": "TERRENO",
}


def _session_desde_gateway(request: Request, db: Session):
    if not MONSTRUO_SSO_SECRET or request is None:
        return None
    raw = request.cookies.get(MONSTRUO_SSO_COOKIE)
    if not raw:
        return None
    tok = raw.split(" ", 1)[1] if raw.startswith("Bearer ") else raw
    try:
        payload = jwt.decode(tok, MONSTRUO_SSO_SECRET, algorithms=[MONSTRUO_SSO_ALG])
    except JWTError:
        return None
    email = (payload.get("sub") or "").strip().lower()
    if "@" not in email:
        return None
    # Autorización contra auth.users del Postgres compartido
    try:
        from sqlalchemy import text as _text

        row = db.execute(
            _text(
                "SELECT role, COALESCE(allowed_modules::text, ''), COALESCE(module_roles::text, '{}'), "
                "COALESCE(first_name, ''), COALESCE(last_name, '') "
                "FROM auth.users WHERE lower(username) = :u "
                "AND COALESCE(is_active::int, 0) = 1"
            ),
            {"u": email},
        ).first()
    except Exception:
        return None  # sin schema auth (modo SQLite standalone) => sin SSO
    if not row:
        return None
    rol_gw = (row[0] or "").strip().lower()
    if rol_gw != "admin" and '"terreneitor"' not in (row[1] or ""):
        return None

    # Rol DENTRO de terreneitor: si el admin lo eligió explícito (module_roles.terreneitor),
    # se usa ese; si no, se deriva del rol global del gateway (comportamiento previo).
    import json as _json
    try:
        _module_roles = _json.loads(row[2] or "{}")
        if not isinstance(_module_roles, dict):
            _module_roles = {}
    except Exception:
        _module_roles = {}
    _explicit = str(_module_roles.get("terreneitor") or "").strip().upper()
    if _explicit in {"TERRENO", "SUPERVISOR", "GERENCIA"}:
        rol_local = _explicit
    else:
        roles_gw = [rol_gw] + [
            str(r).strip().lower() for r in (payload.get("roles") or [])
        ]
        rol_local = next(
            (_SSO_ROL_MAP[r] for r in roles_gw if r in _SSO_ROL_MAP), "TERRENO"
        )

    # Nombre desde la identidad CENTRAL (auth.users es la fuente); si todavía no lo tiene cargado,
    # se deriva del correo como fallback. terreneitor.users es un ESPEJO: no se edita a mano.
    nombre_central = f"{(row[3] or '').strip()} {(row[4] or '').strip()}".strip() \
        or email.split("@")[0].replace(".", " ").title()

    # Usuario local espejo (get-or-create) + re-sincronización de rol y NOMBRE desde el gateway.
    user = db.query(modelos.User).filter(modelos.User.email.ilike(email)).first()
    if not user:
        user = modelos.User(
            email=email,
            name=nombre_central,
            hashed_password=get_db_hash(os.urandom(24).hex()),
            role=rol_local,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif (str(getattr(user.role, "value", user.role)).upper() != str(rol_local).upper()
          or (user.name or "") != nombre_central):
        user.role = rol_local
        user.name = nombre_central
        db.commit()
        db.refresh(user)
    rol_val = getattr(user.role, "value", user.role)
    # Capacidad de crear planes desde Terreno: el flag explícito, o gerencia/supervisor (que ya planifican).
    puede_crear_planes = bool(_module_roles.get("terreneitor_planes")) or str(rol_val).upper() in (
        "ADMIN",
        "SUPERVISOR",
        "GERENCIA",
    )
    return {
        "logged": True,
        "email": user.email,
        "role": rol_val,
        "name": user.name,
        "user_id": user.id,
        "sso": "monstruo",
        "puede_crear_planes": puede_crear_planes,
    }


def puede_crear_planes_flag(db: Session, email: str) -> bool:
    """True si el usuario tiene la capacidad 'terreneitor_planes' en auth.users.module_roles
    (habilita crear planes desde Terreno). Se usa para validar el endpoint en el backend."""
    try:
        from sqlalchemy import text as _text

        row = db.execute(
            _text(
                "SELECT COALESCE(module_roles::text, '{}') FROM auth.users "
                "WHERE lower(username) = :u AND COALESCE(is_active::int, 0) = 1"
            ),
            {"u": (email or "").strip().lower()},
        ).first()
    except Exception:
        return False
    if not row:
        return False
    try:
        import json as _json

        mr = _json.loads(row[0] or "{}")
        return bool(isinstance(mr, dict) and mr.get("terreneitor_planes"))
    except Exception:
        return False


def get_session_data(
    request: Request,
    token: str = Depends(get_token_from_cookie),
    db: Session = Depends(get_db),
):
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return {
                "logged": True,
                "email": payload.get("sub"),
                "role": payload.get("role"),
                "name": payload.get("name"),
                "user_id": payload.get("user_id"),
            }
        except JWTError:
            pass
    sso = _session_desde_gateway(request, db)
    if sso:
        return sso
    return {"logged": False, "role": None}


# --- Wrappers de Seguridad por Rol ---
def require_role(role_esperado: str):
    def role_checker(
        data: dict = Depends(get_session_data), db: Session = Depends(get_db)
    ):
        if not data["logged"]:
            raise HTTPException(status_code=401, detail="No autenticado")
        if data["role"] == "ADMIN":
            user = (
                db.query(modelos.User)
                .filter(modelos.User.id == data["user_id"])
                .first()
            )
            return user
        if data["role"] != role_esperado:
            raise HTTPException(status_code=403, detail="Acceso denegado")
        user = db.query(modelos.User).filter(modelos.User.id == data["user_id"]).first()
        return user

    return role_checker


# ADMIN se fusionó en GERENCIA: los endpoints "admin" (gestión que opera la config de Monstruo)
# ahora los autoriza GERENCIA. require_role mantiene además el bypass para espejos viejos con ADMIN.
require_admin = require_role("GERENCIA")
require_gerencia = require_role("GERENCIA")
require_supervisor = require_role("SUPERVISOR")
require_terreno = require_role("TERRENO")


def require_roles_any(*roles_permitidos: str):
    """AUTHZ-04 (auditoría 2026-06-28): permite cualquiera de varios roles.
    ADMIN siempre pasa. Para gestión de catálogos (clientes) usamos
    ADMIN/GERENCIA/SUPERVISOR — el rol TERRENO (campo) queda excluido."""
    permitidos = set(roles_permitidos) | {"ADMIN"}

    def checker(data: dict = Depends(get_session_data), db: Session = Depends(get_db)):
        if not data["logged"]:
            raise HTTPException(status_code=401, detail="No autenticado")
        if data["role"] not in permitidos:
            raise HTTPException(status_code=403, detail="Acceso denegado")
        return db.query(modelos.User).filter(modelos.User.id == data["user_id"]).first()

    return checker


require_gestion = require_roles_any("GERENCIA", "SUPERVISOR")


def require_session(
    data: dict = Depends(get_session_data), db: Session = Depends(get_db)
):
    if not data["logged"]:
        raise HTTPException(status_code=401, detail="No autenticado")
    user = db.query(modelos.User).filter(modelos.User.id == data["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


def get_current_user(
    data: dict = Depends(get_session_data), db: Session = Depends(get_db)
):
    if not data["logged"]:
        raise HTTPException(status_code=401, detail="No autenticado")
    user = db.query(modelos.User).filter(modelos.User.id == data["user_id"]).first()
    return user
