from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from fundacion.core.env_loader import load_runtime_env
from fundacion.core.version import inject_asset_version

load_runtime_env(Path(__file__).resolve())

from fundacion.backend import router as fundacion_router
from fundacion.backend.routers import sync as sync_router
from fundacion.backend.routers import reportes as reportes_router
from fundacion.backend.routers import sesiones as sesiones_router
from fundacion.backend.auth.router import router as auth_router
from fundacion.backend.auth.admin_users import router as admin_users_router
from fundacion.core import db, deps
from fundacion.core.web import build_login_redirect_url

repo_root = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Fundación API", version="2.0", lifespan=lifespan)

ui_dir = repo_root / "fundacion" / "ui"
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="fundacion_static")

shared_ui_dir = ui_dir / "shared"
if shared_ui_dir.exists():
    app.mount("/shared", StaticFiles(directory=str(shared_ui_dir)), name="shared_static")

# Routers propios de Fundación: app + login propio (sin proxy al gateway).
app.include_router(fundacion_router.router)
app.include_router(sync_router.router)
app.include_router(reportes_router.router)
app.include_router(sesiones_router.router)
app.include_router(auth_router)
app.include_router(admin_users_router)


@app.get("/", response_class=HTMLResponse)
async def get_index(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
):
    try:
        deps.require_session_hybrid(authorization, access_token)
    except Exception:
        return RedirectResponse(build_login_redirect_url(request), status_code=302)
    index_path = ui_dir / "fundacion.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Fundación UI not found")
    return HTMLResponse(inject_asset_version(index_path.read_text(encoding="utf-8")))


# ── Login propio (UI) ────────────────────────────────────────────────────
# Las rutas exactas /login y /login/ se registran ANTES del mount /login para
# que tengan precedencia; el mount sirve los assets (/login/css, /login/js).
login_dir = ui_dir / "login"


@app.get("/login", response_class=HTMLResponse)
@app.get("/login/", response_class=HTMLResponse)
async def login_page():
    page = login_dir / "login.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="login UI not found")
    return HTMLResponse(inject_asset_version(page.read_text(encoding="utf-8")))


if login_dir.exists():
    app.mount("/login", StaticFiles(directory=str(login_dir)), name="login_static")


# ── Telemetría de errores del cliente (sink, no rompe la consola) ────────
@app.post("/api/ops/client-errors")
async def client_errors_sink(request: Request):
    # Compat con shared/js/utilidades.js. Fundación no persiste estos errores
    # (eso era del módulo ops de Monstruo); se aceptan y descartan.
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok", "module": "fundacion"}
