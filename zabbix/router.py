from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter

router = APIRouter(prefix="/api/zabbix", tags=["zabbix"])


def _get_env(nombre: str) -> Optional[str]:
    v = os.getenv(nombre)
    return v.strip() if v else None


@router.get("/estado")
def estado() -> Dict[str, Any]:
    url = _get_env("ZABBIX_URL")
    token = _get_env("ZABBIX_TOKEN")

    if not url or not token:
        return {
            "estado": "ACTIVO_EN_UN_FUTURO",
            "detalle": "Faltan variables ZABBIX_URL/ZABBIX_TOKEN en entorno.",
            "problemas_vivos": None,
            "timestamp": time.time()
        }

    # Implementacion minima (JSON-RPC). No imprimir token.
    t0 = time.time()
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "problem.get",
            "params": {"recent": "true", "sortfield": ["eventid"], "sortorder": "DESC", "limit": 5},
            "auth": token,
            "id": 1
        }
        r = requests.post(url, json=payload, timeout=5)
        lat = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return {"estado": "ERROR", "detalle": f"HTTP {r.status_code}", "problemas_vivos": None, "latencia_ms": lat, "timestamp": time.time()}
        data = r.json()
        problemas = data.get("result", []) if isinstance(data, dict) else []
        return {"estado": "ACTIVO", "detalle": "OK", "problemas_vivos": len(problemas), "latencia_ms": lat, "timestamp": time.time()}
    except Exception as e:
        lat = int((time.time() - t0) * 1000)
        # Placeholder seguro solicitado por usuario
        return {
            "estado": "ACTIVO_EN_UN_FUTURO",
            "detalle": f"Zabbix Offline/Placeholder (Err: {type(e).__name__})",
            "problemas_vivos": None,
            "latencia_ms": lat,
            "timestamp": time.time()
        }


@router.get("/problemas")
def problemas() -> Dict[str, Any]:
    url = _get_env("ZABBIX_URL")
    token = _get_env("ZABBIX_TOKEN")

    if not url or not token:
        return {"estado": "ACTIVO_EN_UN_FUTURO", "problemas": [], "detalle": "Sin credenciales", "timestamp": time.time()}

    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "problem.get",
            "params": {"recent": "true", "sortfield": ["eventid"], "sortorder": "DESC", "limit": 20},
            "auth": token,
            "id": 1
        }
        r = requests.post(url, json=payload, timeout=5)
        if r.status_code != 200:
            return {"estado": "ERROR", "problemas": [], "detalle": f"HTTP {r.status_code}", "timestamp": time.time()}
        data = r.json()
        problemas = data.get("result", []) if isinstance(data, dict) else []
        # Resumen seguro (sin campos sensibles)
        out = []
        for p in problemas:
            out.append({
                "eventid": p.get("eventid"),
                "name": p.get("name"),
                "severity": p.get("severity"),
                "clock": p.get("clock")
            })
        return {"estado": "ACTIVO", "problemas": out, "timestamp": time.time()}
    except Exception as e:
        # Placeholder seguro
        return {"estado": "ACTIVO_EN_UN_FUTURO", "problemas": [], "detalle": f"Zabbix Offline ({type(e).__name__})", "timestamp": time.time()}
