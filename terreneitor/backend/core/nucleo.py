# ========================= nucleo.py (PROD v5.1 - STORAGE CLEAN) =========================
import fcntl
import mimetypes
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.utils.logger import log

# -----------------------------------------------------------------------------
# Middleware: soporte de prefijos /dev y /prod
# -----------------------------------------------------------------------------
# Varias vistas/JS referencian assets y API como /dev/... o /prod/...,
# pero el backend sirve rutas reales sin ese prefijo. Este middleware:
# - Detecta /dev y /prod al inicio del path
# - Setea scope["root_path"] (para construir URLs coherentes si se usa)
# - Stripa el prefijo del scope["path"] para que el router/static funcionen
#
# Esto además permite que /dev/api/* y /prod/api/* funcionen como alias de /api/*.


class EnvPathPrefixMiddleware:
    def __init__(self, app, prefixes=("/dev", "/prod")):
        self.app = app
        self.prefixes = tuple(prefixes)

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path") or ""
            for pref in self.prefixes:
                if path == pref or path.startswith(pref + "/"):
                    new_scope = dict(scope)
                    new_scope["root_path"] = pref
                    stripped = path[len(pref) :] or "/"
                    if not stripped.startswith("/"):
                        stripped = "/" + stripped
                    new_scope["path"] = stripped

                    raw_path = scope.get("raw_path")
                    if isinstance(raw_path, (bytes, bytearray)):
                        raw_pref = pref.encode("utf-8")
                        if raw_path.startswith(raw_pref):
                            new_raw = raw_path[len(raw_pref) :] or b"/"
                            if not new_raw.startswith(b"/"):
                                new_raw = b"/" + new_raw
                            new_scope["raw_path"] = new_raw

                    scope = new_scope
                    break
        return await self.app(scope, receive, send)


# Definicion de Metadatos de la API
tags_metadata = [
    {"name": "Auth", "description": "Autenticación, Login y gestión de Tokens JWT."},
    {
        "name": "Admin",
        "description": "Gestión de proyectos, usuarios y estructura de carpetas (Solo Admin).",
    },
    {
        "name": "Supervisor",
        "description": "Endpoints para rol Supervisor (Dashboard, gestión de tareas).",
    },
    {
        "name": "Terreno",
        "description": "Endpoints para App Móvil de Terreno (Subida de fotos offline).",
    },
]

app = FastAPI(
    title="Terreneitor API Enterprise",
    description="""
    API Backend para el sistema de gestión de proyectos **Terreneitor**.
    Permite la gestión centralizada de obras, fotos y reportes de terreno.

    ## Módulos Principales
    * **Auth**: Seguridad JWT y Rate Limiting.
    * **Admin**: Panel de control total.
    * **Terreno**: API optimizada para baja conectividad.
    """,
    version="6.0.0",
    openapi_tags=tags_metadata,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Debe ir lo más arriba posible para afectar router y estáticos.
app.add_middleware(EnvPathPrefixMiddleware)

# Static mount moved to cerebro.py to prevent route shadowing
# static_dir logic removed from here

# CORS (Permitir subdominios)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://terreno.telconsulting.cl",
        "https://terreneitor.telconsulting.cl",
        "https://supervisor.telconsulting.cl",
        "https://gerencial.telconsulting.cl",
        "https://portal.telconsulting.cl",
        "http://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/common/view")
def serve_file(path: str, thumb: bool = False):  # noqa: C901
    """
    Endpoint universal para servir archivos (Imágenes/Docs).
    Bypass de Auth estricto para evitar problemas de 'Black Photos'.
    """
    import os

    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    if not path:
        raise HTTPException(400, "Path requerido")

    clean_path = os.path.normpath(path)

    # 1. SEGURIDAD: este endpoint NO exige sesión, así que se restringe a servir
    # SOLO archivos dentro de los directorios de datos permitidos (fotos,
    # reportes, cache de thumbnails). Sin esto, ?path=/etc/passwd o la BD
    # quedaban legibles por cualquiera (path traversal + auth bypass).
    _data_parent = os.path.dirname(os.path.realpath(BASE_FILES_DIR))
    _allowed_roots = [
        os.path.realpath(BASE_FILES_DIR),
        os.path.realpath(
            os.environ.get(
                "TERRENEITOR_REPORTES_DIR", os.path.join(_data_parent, "reportes")
            )
        ),
        os.path.realpath(os.path.join(_data_parent, "cache")),
    ]
    _real = os.path.realpath(clean_path)
    if not any(_real == r or _real.startswith(r + os.sep) for r in _allowed_roots):
        raise HTTPException(403, "Acceso denegado")

    if not os.path.exists(clean_path):
        raise HTTPException(404, "Archivo no encontrado")

    if os.path.isdir(clean_path):
        raise HTTPException(400, "Es un directorio")

    # 1.b Formatos que el navegador NO renderiza (HEIC de iPhone, TIFF, BMP):
    # convertir a JPEG al vuelo (miniatura o completa) para que se vean.
    from fastapi.responses import Response as _Resp

    from backend.services import foto_service as _fs

    _ext = os.path.splitext(clean_path)[1].lower()
    if _ext in _fs.NAVEGADOR_NO_SOPORTA:
        _buf = (
            _fs.generate_thumbnail(clean_path)
            if thumb
            else _fs.to_browser_jpeg(clean_path)
        )
        if _buf:
            return _Resp(
                content=_buf.read(),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )

    # 2. Inferencia MIME Robusta
    media_type = None
    lower = clean_path.lower()
    if lower.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif lower.endswith(".png"):
        media_type = "image/png"
    elif lower.endswith(".webp"):
        media_type = "image/webp"

    # 3. THUMBNAIL LOGIC
    if thumb and media_type in ["image/jpeg", "image/png", "image/webp"]:
        # CACHE SETUP — derivado de BASE_FILES_DIR (antes estaba hardcodeado a
        # /srv/terreneitor/... que no existe en el contenedor => 500).
        CACHE_DIR = os.path.join(
            os.path.dirname(os.path.realpath(BASE_FILES_DIR)), "cache", "thumbnails"
        )
        os.makedirs(CACHE_DIR, exist_ok=True)

        import hashlib

        path_hash = hashlib.md5(clean_path.encode("utf-8")).hexdigest()
        cache_filename = f"{path_hash}_thumb.jpg"
        cache_path = os.path.join(CACHE_DIR, cache_filename)

        # A. SERVE FROM CACHE
        if os.path.exists(cache_path):
            return FileResponse(
                cache_path,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )

        # B. GENERATE
        try:
            from PIL import ExifTags, Image

            with Image.open(clean_path) as img:
                # Rotation
                try:
                    for orientation in ExifTags.TAGS.keys():
                        if ExifTags.TAGS[orientation] == "Orientation":
                            break
                    exif = img._getexif()
                    if exif and orientation in exif:
                        if exif[orientation] == 3:
                            img = img.rotate(180, expand=True)
                        elif exif[orientation] == 6:
                            img = img.rotate(270, expand=True)
                        elif exif[orientation] == 8:
                            img = img.rotate(90, expand=True)
                except Exception:
                    pass

                img.thumbnail((300, 300))

                # Convert to RGB (Fix for CMYK/RGBA issues)
                if img.mode != "RGB":
                    img = img.convert("RGB")

                # Save Cache
                img.save(cache_path, "JPEG", quality=70)

                return FileResponse(
                    cache_path,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except Exception as e:  # noqa: B904
            # Fallback to full
            # Fallback to full
            log.error(
                f"[THUMBNAIL_ERROR] Failed to generate thumb for {clean_path}: {e}"
            )
            pass

    # 4. FULL FILE FALLBACK
    headers = {"Content-Disposition": "inline", "Cache-Control": "no-cache"}
    return FileResponse(clean_path, media_type=media_type, headers=headers)


# Base directory for storage files (configurable)
BASE_FILES_DIR = os.environ.get("BASE_FILES_DIR", "/srv/terreneitor/data/files")


def get_reports_dir() -> str:
    """
    Resuelve el directorio de reportes DOCX de forma consistente entre
    entorno local (/srv/terreneitor/...) y Docker (/app/data/...).

    Prioridad:
    1) TERRENEITOR_REPORTES_DIR (si está configurada)
    2) Hermano de BASE_FILES_DIR: <base_parent>/reportes
    """
    env_reports_dir = os.environ.get("TERRENEITOR_REPORTES_DIR")
    if env_reports_dir:
        return os.path.abspath(env_reports_dir)

    base_files_dir = os.path.abspath(os.environ.get("BASE_FILES_DIR", BASE_FILES_DIR))
    return os.path.join(os.path.dirname(base_files_dir), "reportes")


def ensure_reports_dir() -> str:
    """Asegura que exista el directorio de reportes y retorna su ruta."""
    reports_dir = get_reports_dir()
    os.makedirs(reports_dir, exist_ok=True, mode=0o775)
    return reports_dir


def _resolve_python_executable() -> str:
    candidates = [
        os.environ.get("PYTHON_EXECUTABLE"),
        sys.executable,
        "/usr/bin/python3",
        "/usr/bin/python",
        "python3",
        "python",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isabs(candidate) and not os.path.exists(candidate):
            continue
        return candidate
    return "python3"


# Si en algún endpoint se ejecuta scanner por subprocess, estas rutas deben ser reales:
SCANNER_SCRIPT_PATH = os.environ.get(
    "SCANNER_SCRIPT_PATH",
    os.path.join(os.path.dirname(__file__), "scanner.py"),
)
PYTHON_EXECUTABLE = _resolve_python_executable()

QUARANTINE_DIR_NAME = "_PENDIENTE_METADATOS"
VALIDATION_DIR_NAME = "_POR_VALIDAR"
ARCHIVE_DIR_NAME = "_ARCHIVADOS"
RETURNED_DIR_NAME = "_DEVUELTAS"
TRASH_DIR_NAME = "_PAPELERA"
LOCKS_DIR = os.environ.get("TERRENEITOR_LOCKS_DIR", "/srv/terreneitor/data/locks")

# BASE DE DATOS MULTI-TENANT
DB_DIR = os.environ.get("TERRENEITOR_DB_DIR", "/srv/terreneitor/data/db")
DEFAULT_DB_FILE = "terreneitor.db"

# URL única de base de datos (modo Monstruo: Postgres central, schema terreneitor).
# Si está seteada, reemplaza el multi-tenant SQLite: todos los hosts usan la misma
# base. Ej: postgresql+psycopg2://user:pass@db:5432/monstruo_dev?options=-csearch_path%3Dterreneitor,public
DATABASE_URL = os.environ.get("TERRENEITOR_DATABASE_URL", "").strip()

_engines = {}
_engines_lock = threading.Lock()


def get_db_path(tenant_name: str) -> str:
    os.makedirs(DB_DIR, exist_ok=True)
    # Sanitizar nombre
    clean_name = "".join(c for c in tenant_name if c.isalnum() or c in ("_", "-"))
    if not clean_name:
        clean_name = "default"
    return os.path.join(DB_DIR, f"{clean_name}.db")


def get_engine(tenant_name: str = "default") -> Engine:
    # Modo URL única (Postgres en Monstruo): ignora el tenant, una sola base.
    if DATABASE_URL:
        with _engines_lock:
            if DATABASE_URL not in _engines:
                eng = create_engine(
                    DATABASE_URL,
                    pool_pre_ping=True,
                    pool_size=5,
                    max_overflow=10,
                )
                _engines[DATABASE_URL] = eng
                log.info("[DB] Engine creado para TERRENEITOR_DATABASE_URL (externa)")
            return _engines[DATABASE_URL]

    # Mapeo de subdominios a nombres de archivo DB
    # Ejemplo: 'terreneitor.telconsulting.cl' -> 'proyectos' (default)
    # 'clienteA.telconsulting.cl' -> 'clienteA'

    if (
        "terreneitor" in tenant_name
        or "terreno" in tenant_name
        or "default" in tenant_name
        or "portal" in tenant_name
        or "gerencia" in tenant_name
        or "supervisor" in tenant_name
        or "localhost" in tenant_name
        or tenant_name.startswith("127.")
        or tenant_name.startswith("192.168.")
        or tenant_name.startswith("10.")
    ):
        db_name = "terreneitor"
    else:
        db_name = tenant_name.split(".")[0]  # 'clienteA.com' -> 'clienteA'

    db_path = get_db_path(db_name)

    with _engines_lock:
        if db_path not in _engines:
            # Crear engine si no existe
            db_url = f"sqlite:///{db_path}"
            _conn_args = {"check_same_thread": False, "timeout": 30}
            # StaticPool (1 conexion compartida por todos los hilos) SOLO para BD
            # en memoria (tests). En BD de archivo causaba que requests
            # concurrentes entrelazaran transacciones; el pool por defecto da una
            # conexion por hilo. WAL + busy_timeout permiten la concurrencia.
            if ":memory:" in db_url:
                eng = create_engine(
                    db_url,
                    connect_args=_conn_args,
                    poolclass=StaticPool,
                    pool_pre_ping=True,
                )
            else:
                eng = create_engine(db_url, connect_args=_conn_args, pool_pre_ping=True)
            # Listeners (Foreign Keys)
            event.listen(eng, "connect", set_sqlite_pragma)
            _engines[db_path] = eng
            log.info(f"[DB] Engine creado para: {db_name} ({db_path})")

        return _engines[db_path]


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Listener global (clase Engine): con Postgres (psycopg2) los PRAGMA no
    # existen y romperian la conexion. Solo aplica a SQLite.
    import sqlite3 as _sqlite3

    if not isinstance(dbapi_connection, _sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# --- LEGACY SUPPORT (Para cerebro.py y scripts antiguos) ---
DATABASE_FILE = os.path.join(DB_DIR, DEFAULT_DB_FILE)
engine = get_engine("default")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# HELPERS
storage_refresh_lock = threading.Lock()


@contextmanager
def plan_lock(plan_id: int, timeout_sec: int = 120):
    os.makedirs(LOCKS_DIR, exist_ok=True)
    lock_path = os.path.join(LOCKS_DIR, f"plan_{plan_id}.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o664)
    f = os.fdopen(fd, "r+")
    start = time.time()
    try:
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if (time.time() - start) > timeout_sec:
                    raise TimeoutError(f"plan_lock timeout for plan_id={plan_id}")
                time.sleep(0.1)
        yield
    finally:
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            f.close()
        except Exception:
            pass


def run_storage_index_refresh():
    return


def natural_sort_key(s):
    if not isinstance(s, str):
        s = str(s)
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"([0-9]+)", s)
    ]


mimetypes.add_type("image/webp", ".webp")

# === AUTO FIX PENDIENTE METADATA / VALIDACION ===
from backend.models.modelos import AsignacionPlan, EstadoItemEnum, EstadoPlanEnum

AUTO_FIX_INTERVAL = 1800  # 30 minutos


def auto_fix_metadata_states():
    db = SessionLocal()
    try:
        asignaciones = (
            db.query(AsignacionPlan)
            .filter(
                AsignacionPlan.estado.in_(
                    [EstadoItemEnum.PENDIENTE_EXIF, EstadoItemEnum.COMPLETADA_TERRENO]
                )
            )
            .all()
        )

        corregidos = 0
        for a in asignaciones:
            item_path = Path(a.item.ruta_item)
            cuarentena = item_path / QUARANTINE_DIR_NAME
            validar = item_path / VALIDATION_DIR_NAME

            tiene_cuarentena = cuarentena.exists() and any(cuarentena.iterdir())
            tiene_validar = validar.exists() and any(validar.iterdir())

            # Caso 1: No hay en cuarentena pero sí en por validar
            if not tiene_cuarentena and tiene_validar:
                if a.estado != EstadoItemEnum.COMPLETADA_TERRENO:
                    a.estado = EstadoItemEnum.COMPLETADA_TERRENO
                    corregidos += 1

            # Caso 2: No hay fotos ni en cuarentena ni en validar
            elif not tiene_cuarentena and not tiene_validar:
                if a.estado != EstadoItemEnum.ASIGNADA:
                    a.estado = EstadoItemEnum.ASIGNADA
                    corregidos += 1

            # Reabrir plan si estaba cerrado
            if a.plan.estado_plan == EstadoPlanEnum.CERRADO:
                a.plan.estado_plan = EstadoPlanEnum.ABIERTO

        if corregidos > 0:
            db.commit()
            log.info(
                f"[AUTO-FIX] {corregidos} asignaciones corregidas automáticamente."
            )
    except Exception as e:  # noqa: B904
        log.error(f"[AUTO-FIX ERROR] {e}")
    finally:
        db.close()


def _start_autofix_timer(delay_seconds: int) -> None:
    t = threading.Timer(delay_seconds, auto_fix_metadata_states)
    t.daemon = True
    t.start()


_disable_autofix = (
    os.environ.get("TERRENEITOR_DISABLE_AUTOFIX", "0") == "1"
    or os.environ.get("ENV") == "test"
    or "PYTEST_CURRENT_TEST" in os.environ
)
if not _disable_autofix:
    _start_autofix_timer(AUTO_FIX_INTERVAL)
    _start_autofix_timer(60)
