from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Cookie, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles

from plataforma.core.env_loader import load_runtime_env

load_runtime_env(Path(__file__).resolve())

from ia.backend import router as ia_router
from plataforma.core import db, deps
from plataforma.core.web import build_login_redirect_url

repo_root = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Monstruo - IA API", version="1.0", lifespan=lifespan)

ui_dir = repo_root / "ia" / "ui"
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="ia_static")

shared_ui_dir = repo_root / "gateway" / "ui" / "shared" / "ui"
if shared_ui_dir.exists():
    app.mount("/shared", StaticFiles(directory=str(shared_ui_dir)), name="shared_static")

app.include_router(ia_router.router)


async def _proxy_to_gateway(target_path: str, request: Request) -> FastAPIResponse:
    async with httpx.AsyncClient() as client:
        content = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None)
        response = await client.request(
            request.method,
            f"http://gateway:9001{target_path}",
            content=content,
            headers=headers,
            params=request.query_params,
            timeout=30.0,
        )
        passthrough_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in {"content-length", "transfer-encoding", "connection", "content-encoding"}
        }
        return FastAPIResponse(
            content=response.content,
            status_code=response.status_code,
            headers=passthrough_headers,
            media_type=response.headers.get("content-type"),
        )


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
    index_path = ui_dir / "ia.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="IA UI not found")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def gateway_api_proxy(path: str, request: Request):
    return await _proxy_to_gateway(f"/api/{path}", request)


@app.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def gateway_auth_proxy(path: str, request: Request):
    return await _proxy_to_gateway(f"/auth/{path}", request)


@app.get("/health")
async def health():
    return {"status": "ok", "module": "ia"}
