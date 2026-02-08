#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

def ahora_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def cargar_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def conectar(db: str) -> sqlite3.Connection:
    con = sqlite3.connect(db, timeout=30)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con

def insertar_evento(con: sqlite3.Connection, severidad: str, resumen: str, detalle: dict) -> None:
    con.execute(
        "INSERT INTO eventos(ts,tipo,severidad,origen,ruta,resumen,detalle_json) VALUES (?,?,?,?,?,?,?)",
        (
            ahora_utc_iso(),
            "auditoria_nombres_prohibidos",
            severidad,
            "saneador_nombres_prohibidos",
            None,
            resumen,
            json.dumps(detalle, ensure_ascii=False),
        ),
    )
    con.commit()

def coincide_prohibido(nombre: str, patrones: List[str]) -> Optional[str]:
    n = nombre.lower()
    for p in patrones:
        pl = p.lower()
        if pl.startswith(".") and n.endswith(pl):
            return p
        if pl in n:
            return p
    return None

def es_bajo_backups(path: Path, backups_root: Path) -> bool:
    try:
        return str(path.resolve()).startswith(str(backups_root.resolve()) + os.sep)
    except Exception:
        return False

def accion_sugerida(nombre: str, patron: str) -> str:
    n = nombre.lower()
    if n.endswith(".bak") or n.endswith(".old") or ("_backup" in n):
        return "mover_a_backups"
    return "revisar_manual"

def iterar_archivos(base: Path, excluir_dirs: Set[str]) -> List[Path]:
    out: List[Path] = []
    for raiz, dirs, files in os.walk(str(base), topdown=True):
        dirs[:] = [d for d in dirs if d not in excluir_dirs]
        for fn in files:
            out.append(Path(raiz) / fn)
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="/srv/monstruo/ops/guardian/configuracion_guardian.json")
    ap.add_argument("--db", default="/srv/monstruo/ops/guardian/guardian.sqlite")
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()

    cfg = cargar_json(args.config)
    rutas = cfg.get("rutas", {})
    raiz = Path(rutas.get("raiz_proyecto", "/srv/monstruo"))
    backups_root = Path(rutas.get("carpeta_backups", "/srv/monstruo/backups"))

    vig = cfg.get("vigilante_archivos", {}) or {}
    excluir = set(vig.get("excluir_subrutas", ["backups", "venv", ".git", "__pycache__"]))
    patrones = vig.get("patrones_prohibidos", [".bak", ".old", "_backup", "_final", "_v2", "v1", "v2"])

    hallazgos: List[dict] = []
    for p in iterar_archivos(raiz, excluir_dirs=excluir):
        try:
            pr = p.resolve()
        except Exception:
            continue
        if es_bajo_backups(pr, backups_root):
            continue

        patron = coincide_prohibido(pr.name, patrones)
        if not patron:
            continue

        try:
            st = pr.stat()
            tam = int(st.st_size)
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
        except Exception:
            tam = None
            mtime = None

        hallazgos.append({
            "ruta": str(pr),
            "nombre": pr.name,
            "patron": patron,
            "accion_sugerida": accion_sugerida(pr.name, patron),
            "tamano": tam,
            "mtime_utc": mtime,
        })

    resumen = {
        "ts_utc": ahora_utc_iso(),
        "raiz": str(raiz),
        "backups_root": str(backups_root),
        "excluir": sorted(list(excluir)),
        "patrones_prohibidos": patrones,
        "total_hallazgos": len(hallazgos),
        "por_accion": {
            "mover_a_backups": sum(1 for h in hallazgos if h["accion_sugerida"] == "mover_a_backups"),
            "revisar_manual": sum(1 for h in hallazgos if h["accion_sugerida"] == "revisar_manual"),
        },
        "hallazgos": hallazgos,
    }

    out_path = Path(args.salida)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    severidad = "INFO" if len(hallazgos) == 0 else "CRITICAL"
    con = conectar(args.db)
    try:
        insertar_evento(
            con,
            severidad=severidad,
            resumen=f"Reporte nombres prohibidos fuera de backups/: {len(hallazgos)} hallazgos",
            detalle={"salida": str(out_path), "por_accion": resumen["por_accion"]},
        )
    finally:
        con.close()

    print(json.dumps({"ok": True, "salida": str(out_path), "total_hallazgos": len(hallazgos), "por_accion": resumen["por_accion"]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
