from fastapi import Cookie, FastAPI, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path

import sys

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
sys.path.append(str(Path(__file__).parent))
import router as bodega_router
from plataforma.core import deps
from plataforma.core.web import build_login_redirect_url

app = FastAPI(title="Monstruo - Bodega (WMS) API", version="1.0")

# Servir estáticos propios del módulo
ui_dir = Path(__file__).parent / "ui"
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="bodega_static")

# Servir estáticos compartidos desde el canon del gateway
shared_ui_dir = repo_root / "gateway" / "shared" / "ui"
if shared_ui_dir.exists():
    app.mount("/shared", StaticFiles(directory=str(shared_ui_dir)), name="shared_static")

app.include_router(bodega_router.router)

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
    index_path = ui_dir / "bodega.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "Bodega UI not found"

@app.get("/health")
async def health():
    return {"status": "ok", "module": "bodega"}
