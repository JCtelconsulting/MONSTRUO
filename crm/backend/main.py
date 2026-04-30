from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, FastAPI, Header, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from plataforma.core.env_loader import load_runtime_env

load_runtime_env(Path(__file__).resolve())

from crm.backend import router as crm_router
from plataforma.core import db, deps
from plataforma.core.web import build_login_redirect_url

repo_root = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Monstruo - CRM API", version="1.0", lifespan=lifespan)

ui_dir = repo_root / "crm" / "ui"
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="crm_static")

shared_ui_dir = repo_root / "gateway" / "ui" / "shared" / "ui"
if shared_ui_dir.exists():
    app.mount("/shared", StaticFiles(directory=str(shared_ui_dir)), name="shared_static")

app.include_router(crm_router.router)


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
    index_path = ui_dir / "crm.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("CRM UI not found", status_code=404)


@app.get("/health")
async def health():
    return {"status": "ok", "module": "crm"}
