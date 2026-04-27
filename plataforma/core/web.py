from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import RedirectResponse


def _normalize_prefix(prefix: str | None) -> str:
    normalized = str(prefix or "").strip().rstrip("/")
    if not normalized:
        return ""
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _detect_dev_prefix_from_url(raw_url: str | None) -> str:
    candidate = str(raw_url or "").strip()
    if not candidate:
        return ""
    path = urlsplit(candidate).path if "://" in candidate else candidate
    path = str(path or "").strip()
    if path == "/dev" or path.startswith("/dev/"):
        return "/dev"
    return ""


def get_public_prefix(request: Request, root_path: str = "") -> str:
    direct_candidates = (
        request.headers.get("x-forwarded-prefix"),
        request.headers.get("x-script-name"),
        request.scope.get("root_path"),
        root_path,
    )
    for candidate in direct_candidates:
        prefix = _normalize_prefix(candidate)
        if prefix:
            return prefix

    url_candidates = (
        request.headers.get("x-original-uri"),
        request.headers.get("x-forwarded-uri"),
        request.headers.get("x-original-url"),
        request.headers.get("referer"),
        str(request.url.path or ""),
    )
    for candidate in url_candidates:
        prefix = _detect_dev_prefix_from_url(candidate)
        if prefix:
            return prefix

    return ""


def build_login_redirect_url(
    request: Request,
    *,
    root_path: str = "",
    local_gateway_port: int = 9001,
    local_login_path: str = "/",
) -> str:
    prefix = get_public_prefix(request, root_path=root_path)
    forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",", 1)[0].strip()
    host = (forwarded_host or request.headers.get("host") or request.url.hostname or "").split(":")[0].strip().lower()
    login_path = local_login_path if local_login_path.startswith("/") else f"/{local_login_path}"
    if host.endswith(".telconsulting.cl"):
        return f"https://login.telconsulting.cl{prefix}{login_path}"

    scheme = request.url.scheme or "http"
    local_host = request.url.hostname or "127.0.0.1"
    return f"{scheme}://{local_host}:{local_gateway_port}{prefix}{login_path}"


def redirect_to_login(
    request: Request,
    *,
    root_path: str = "",
    status_code: int = 302,
    local_gateway_port: int = 9001,
    local_login_path: str = "/",
) -> RedirectResponse:
    return RedirectResponse(
        build_login_redirect_url(
            request,
            root_path=root_path,
            local_gateway_port=local_gateway_port,
            local_login_path=local_login_path,
        ),
        status_code=status_code,
    )
