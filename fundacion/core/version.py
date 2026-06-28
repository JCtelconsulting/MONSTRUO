"""
Versión del código en runtime — usada para cache-busting de assets estáticos.

ASSET_VERSION se computa una vez al import:
- En containers con .git: usa `git rev-parse --short HEAD`.
- Sin git (o falla): fallback al timestamp del archivo de versión, o "dev".

Uso típico desde gateway/backend/main.py:
    from fundacion.core.version import ASSET_VERSION
    html = html.replace("?v=ASSET_VERSION", f"?v={ASSET_VERSION}")

Convención: en HTML, en lugar de `<link href="x.css?v=75">`, escribir
`<link href="x.css?v=ASSET_VERSION">`. El gateway reemplaza al servir.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _compute_asset_version() -> str:
    # 1. Variable de entorno explícita (CI/CD puede setearla en deploy)
    env_value = os.getenv("ASSET_VERSION", "").strip()
    if env_value:
        return env_value

    # 2. git rev-parse --short HEAD
    try:
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=2,
        )
        sha = result.stdout.strip()
        if result.returncode == 0 and sha:
            return sha
    except Exception:
        pass

    # 3. Fallback: timestamp del archivo (cambia cuando se redeploy)
    try:
        return str(int(Path(__file__).stat().st_mtime))
    except Exception:
        return "dev"


ASSET_VERSION: str = _compute_asset_version()


def inject_asset_version(html: str) -> str:
    """Sustituye `?v=ASSET_VERSION` por el SHA actual e inyecta `window.ASSET_VERSION`.

    Pensado para usarse al servir el HTML de cada app (gateway + apps proxy).
    Es idempotente: si el HTML ya no contiene `?v=ASSET_VERSION` no rompe nada.
    """
    html = html.replace("?v=ASSET_VERSION", f"?v={ASSET_VERSION}")
    version_script = f'<script>window.ASSET_VERSION = "{ASSET_VERSION}";</script>'
    if "</head>" in html:
        html = html.replace("</head>", f"    {version_script}\n</head>", 1)
    return html
