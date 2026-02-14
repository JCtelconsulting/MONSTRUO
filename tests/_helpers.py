from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests


def env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def guard_prod_target(base_url: str, allow_prod: bool) -> None:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    target = base_url.lower()
    looks_prod = "prod" in host or "/prod" in path or "/prod/" in target
    if looks_prod and not allow_prod:
        raise RuntimeError(
            "Ejecucion bloqueada: la URL parece PROD. "
            "Usa --allow-prod solo si lo autorizaste explicitamente."
        )


def require_credentials(username: Optional[str], password: Optional[str]) -> None:
    if username and password:
        return
    raise RuntimeError(
        "Faltan credenciales. Define MONSTRUO_TEST_USER y MONSTRUO_TEST_PASSWORD "
        "o usa --user/--password."
    )


def build_session(
    base_url: str,
    username: str,
    password: str,
    timeout: int = 15,
) -> Dict[str, Any]:
    session = requests.Session()
    url = f"{normalize_base_url(base_url)}/api/auth/login"
    resp = session.post(
        url,
        json={"email": username, "password": password},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login fallo ({resp.status_code}): {resp.text}")
    data = resp.json()
    token = data.get("token") or data.get("access_token")
    if not token:
        raise RuntimeError(f"Login sin token en respuesta: {data}")
    session.cookies.set("access_token", token)
    return {"session": session, "login": data, "token": token}


def as_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception as exc:
        raise RuntimeError(f"Respuesta no-JSON ({resp.status_code}): {resp.text}") from exc
