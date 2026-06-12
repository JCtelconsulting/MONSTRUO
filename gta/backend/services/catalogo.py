"""Servicio de catálogo de procesos: escanea gta/data/procesos y devuelve un índice navegable."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Tipos de archivo soportados (descargables como proceso)
ALLOWED_EXTENSIONS = {".docx", ".doc", ".pdf", ".pptx", ".ppt", ".xlsx", ".xls", ".txt", ".md"}

# Iconos sugeridos por extensión (Font Awesome)
ICON_MAP = {
    ".docx": "fa-file-word",
    ".doc":  "fa-file-word",
    ".pdf":  "fa-file-pdf",
    ".pptx": "fa-file-powerpoint",
    ".ppt":  "fa-file-powerpoint",
    ".xlsx": "fa-file-excel",
    ".xls":  "fa-file-excel",
    ".txt":  "fa-file-lines",
    ".md":   "fa-file-lines",
}


def _data_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "procesos"


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _isoformat(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def scan_catalog() -> Dict:
    """Escanea data/procesos y devuelve estructura jerárquica para la UI."""
    root = _data_root()
    if not root.exists():
        return {"areas": [], "total_procesos": 0, "scanned_at": _isoformat(datetime.now(timezone.utc).timestamp()), "missing_root": True}

    areas: Dict[str, Dict] = {}
    sueltos: List[Dict] = []
    total_files = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue

        total_files += 1
        rel_path = path.relative_to(root).as_posix()
        parts = rel_path.split("/")

        st = path.stat()
        item = {
            "name": path.stem,
            "filename": path.name,
            "path": rel_path,
            "ext": path.suffix.lower().lstrip("."),
            "icon": ICON_MAP.get(path.suffix.lower(), "fa-file"),
            "size": st.st_size,
            "size_label": _format_size(st.st_size),
            "modified_at": _isoformat(st.st_mtime),
        }

        # Si no está dentro de un área, va a "sueltos"
        if len(parts) == 1:
            sueltos.append(item)
            continue

        area_code = parts[0]
        sub_code = parts[1] if len(parts) >= 3 else None

        area = areas.setdefault(area_code, {
            "code": area_code,
            "files": [],
            "subareas": {},
            "count": 0,
        })
        area["count"] += 1

        if sub_code is None:
            area["files"].append(item)
        else:
            sub = area["subareas"].setdefault(sub_code, {"code": sub_code, "files": [], "count": 0})
            sub["files"].append(item)
            sub["count"] += 1

    # Convertir subareas dict → list
    areas_list = []
    for code, area in sorted(areas.items()):
        area["subareas"] = sorted(area["subareas"].values(), key=lambda s: s["code"])
        areas_list.append(area)

    return {
        "areas": areas_list,
        "sueltos": sueltos,
        "total_procesos": total_files,
        "scanned_at": _isoformat(datetime.now(timezone.utc).timestamp()),
    }


def resolve_safe_path(rel_path: str) -> Optional[Path]:
    """Valida que rel_path no escape de data/procesos y devuelve la ruta absoluta."""
    root = _data_root().resolve()
    if not rel_path:
        return None
    try:
        candidate = (root / rel_path).resolve()
        candidate.relative_to(root)
    except (ValueError, OSError):
        return None
    if not candidate.is_file():
        return None
    if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        return None
    return candidate
