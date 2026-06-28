from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Cookie, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles

from plataforma.core.env_loader import load_runtime_env
from plataforma.core.version import inject_asset_version

load_runtime_env(Path(__file__).resolve())

from gta.backend import router as gta_router
from gta.backend.jobs import sla_check as gta_sla_job
from plataforma.core import db, deps, jobs_engine
from plataforma.core.config import settings as app_settings
from plataforma.core.web import build_login_redirect_url

logger = logging.getLogger(__name__)

# SECRET-guard (auditoría 2026-06-28): mismo fail-closed que gateway/ticketera.
# GTA no emite JWTs (proxya el login al gateway) pero SÍ los verifica con la
# SECRET_KEY compartida vía plataforma.core; el guard es defensa en profundidad.
_WEAK_SECRET_MARKERS = {
    "",
    "CAMBIAME_ESTO_ES_INSEGURO_F8A9",
    "replace_me",
    "dev_only_change_me",
}


def _is_weak_secret(secret_key: str) -> bool:
    normalized = str(secret_key or "").strip()
    return normalized in _WEAK_SECRET_MARKERS or len(normalized) < 32


repo_root = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(app: FastAPI):
    env_type = str(getattr(app_settings, "ENV_TYPE", "dev") or "dev").strip().lower()
    if _is_weak_secret(getattr(app_settings, "SECRET_KEY", "")):
        if env_type == "prod":
            raise RuntimeError("CRITICAL: SECRET_KEY inseguro en PROD.")
        app_settings.SECRET_KEY = secrets.token_urlsafe(64)
        logger.warning("[SECURITY] SECRET_KEY inseguro/ausente. Se generó una clave efímera.")
    db.init_db()

    # Registrar y arrancar jobs del GTA
    jobs_engine.register_job(gta_sla_job.JOB_TYPE, gta_sla_job.gta_sla_check)
    await jobs_engine.enqueue_unique_job(
        gta_sla_job.JOB_TYPE,
        payload={"recurring": True},
        max_retries=1,
    )
    # Worker loop para procesar los jobs encolados
    asyncio.create_task(jobs_engine.worker_loop())

    yield


app = FastAPI(title="Monstruo - GTA API", version="1.0", lifespan=lifespan)

ui_dir = repo_root / "gta" / "ui"
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="gta_static")

shared_ui_dir = repo_root / "gateway" / "ui" / "shared" / "ui"
if shared_ui_dir.exists():
    app.mount("/shared", StaticFiles(directory=str(shared_ui_dir)), name="shared_static")

app.include_router(gta_router.router)


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
            key: value
            for key, value in response.headers.items()
            if key.lower() not in {"content-length", "transfer-encoding", "connection", "content-encoding"}
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
    index_path = ui_dir / "gta.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="GTA UI not found")
    return HTMLResponse(inject_asset_version(index_path.read_text(encoding="utf-8")))


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def gateway_api_proxy(path: str, request: Request):
    return await _proxy_to_gateway(f"/api/{path}", request)


@app.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def gateway_auth_proxy(path: str, request: Request):
    return await _proxy_to_gateway(f"/auth/{path}", request)


@app.get("/health")
async def health():
    return {"status": "ok", "module": "gta"}
