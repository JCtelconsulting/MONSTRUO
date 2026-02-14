#!/usr/bin/env python3
# Vigilante de registros (logs) para MONSTRUO:
# - Registra eventos en SQLite cuando detecta patrones de error.
# - Soporta modo "archivo" (para pruebas) y "journalctl" (para produccion).
# - Deduplicacion simple para evitar spam.

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

def ahora_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def cargar_cfg(ruta: str) -> dict:
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)

class Emisor:
    def __init__(self, db: str):
        self.con = sqlite3.connect(db, timeout=30)
        self.con.execute("PRAGMA journal_mode=WAL;")
        self.con.execute("PRAGMA synchronous=NORMAL;")

    def cerrar(self):
        try:
            self.con.close()
        except Exception:
            pass

    def evento(self, tipo: str, severidad: str, origen: str, ruta: Optional[str], resumen: str, detalle: Optional[dict] = None):
        ts = ahora_utc_iso()
        dj = json.dumps(detalle, ensure_ascii=False) if detalle is not None else None
        self.con.execute(
            "INSERT INTO eventos(ts,tipo,severidad,origen,ruta,resumen,detalle_json) VALUES (?,?,?,?,?,?,?)",
            (ts, tipo, severidad, origen, ruta, resumen, dj),
        )
        self.con.commit()

def elegir_bloque_logs(cfg: dict) -> dict:
    # Compatibilidad: aceptar "vigilante_registros" o el heredado "vigilante_logs"
    if "vigilante_registros" in cfg:
        return cfg["vigilante_registros"]
    return cfg.get("vigilante_logs", {})

def clasificar_severidad(patron: str) -> str:
    p = patron.lower()
    if "traceback" in p or "exception" in p:
        return "CRITICAL"
    if "error" in p or "integrityerror" in p or "operationalerror" in p:
        return "WARN"
    return "INFO"

def detectar_patron(linea: str, patrones: List[str]) -> Optional[str]:
    for p in patrones:
        if p in linea:
            return p
    return None

def debe_emitir(key: str, vistos: Dict[str, float], ventana: float) -> bool:
    ahora = time.time()
    t = vistos.get(key)
    if t is None or (ahora - t) >= ventana:
        vistos[key] = ahora
        # compactar dict si crece demasiado
        if len(vistos) > 5000:
            corte = ahora - (ventana * 2.0)
            for k in list(vistos.keys()):
                if vistos[k] < corte:
                    del vistos[k]
        return True
    return False

def procesar_linea(linea: str, patrones: List[str], em: Emisor, vistos: Dict[str, float], ventana: float, origen: str, ruta_origen: Optional[str]):
    patron = detectar_patron(linea, patrones)
    if not patron:
        return
    severidad = clasificar_severidad(patron)
    key = f"{patron}|{linea.strip()}"
    if not debe_emitir(key, vistos, ventana):
        return
    em.evento(
        tipo="registro_error_detectado",
        severidad=severidad,
        origen=origen,
        ruta=ruta_origen,
        resumen=f"Patron detectado en registros: {patron}",
        detalle={"patron": patron, "linea": linea.strip()},
    )

def leer_archivo(ruta: str) -> List[str]:
    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()

def leer_journalctl_unidad(unidad: str, seguir: bool) -> subprocess.Popen:
    # -o cat: linea limpia
    # -n 0 cuando seguimos para no traer backlog gigante
    cmd = ["journalctl", "-u", unidad, "-o", "cat"]
    if seguir:
        cmd += ["-f", "-n", "0"]
    else:
        cmd += ["-n", "200"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="/srv/monstruo_dev/ops/guardian/config/configuracion_guardian.json")
    ap.add_argument("--modo", choices=["archivo", "journalctl"], default=None)
    ap.add_argument("--archivo", default=None)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--ventana_deduplicacion", type=float, default=60.0)
    args = ap.parse_args()

    cfg = cargar_cfg(args.config)
    bloque = elegir_bloque_logs(cfg)

    modo_cfg = bloque.get("modo", "journalctl")
    modo = args.modo or modo_cfg

    patrones = bloque.get("patrones_error", ["Traceback", "ERROR", "Exception"])
    unidad = bloque.get("unidad_systemd", "monstruo-backend")

    db = cfg["rutas"]["bd_eventos"]
    em = Emisor(db)
    vistos: Dict[str, float] = {}

    try:
        if modo == "archivo":
            if not args.archivo:
                em.evento("vigilante_registros_error", "WARN", "vigilante_registros", None, "Modo archivo sin --archivo", None)
                return 2
            lineas = leer_archivo(args.archivo)
            for ln in lineas:
                procesar_linea(ln, patrones, em, vistos, args.ventana_deduplicacion, "vigilante_registros", args.archivo)
            return 0

        # journalctl
        seguir = not args.once
        p = leer_journalctl_unidad(unidad, seguir=seguir)

        if p.stdout is None or p.stderr is None:
            em.evento("vigilante_registros_error", "WARN", "vigilante_registros", None, "No se pudo leer stdout/stderr de journalctl", {"unidad": unidad})
            return 2

        if args.once:
            out = p.communicate(timeout=10)[0]
            for ln in out.splitlines():
                procesar_linea(ln, patrones, em, vistos, args.ventana_deduplicacion, "vigilante_registros", f"journalctl:{unidad}")
            return 0

        # seguir
        for ln in p.stdout:
            procesar_linea(ln, patrones, em, vistos, args.ventana_deduplicacion, "vigilante_registros", f"journalctl:{unidad}")

        return 0

    except subprocess.TimeoutExpired:
        em.evento("vigilante_registros_error", "WARN", "vigilante_registros", None, "Timeout leyendo journalctl", {"unidad": unidad})
        return 2
    except FileNotFoundError:
        em.evento("vigilante_registros_error", "WARN", "vigilante_registros", None, "journalctl no disponible", None)
        return 2
    finally:
        em.cerrar()

if __name__ == "__main__":
    raise SystemExit(main())
