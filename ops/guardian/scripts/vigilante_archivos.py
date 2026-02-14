#!/usr/bin/env python3
# Vigilante de archivos para MONSTRUO (solo lectura + eventos en SQLite)
# Reglas clave:
# - No modifica archivos.
# - Detecta nombres prohibidos (.bak/.old/_backup/_final/_v2/v1/v2) fuera de backups/ y registra CRITICAL.
# - Registra INFO en creacion/modificacion/eliminacion para extensiones de interes.

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


DETENER = False


def _manejar_senal(_sig, _frame):
    global DETENER
    DETENER = True


def ahora_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cargar_configuracion(ruta_cfg: str) -> dict:
    with open(ruta_cfg, "r", encoding="utf-8") as f:
        return json.load(f)


def ruta_tiene_componente(ruta: Path, componentes: Set[str]) -> bool:
    return any(p in componentes for p in ruta.parts)


def es_bajo_backups(ruta: Path) -> bool:
    return "backups" in ruta.parts


def coincide_patron_prohibido(nombre: str, patrones: List[str]) -> Optional[str]:
    nombre_lower = nombre.lower()
    for p in patrones:
        if p.startswith(".") and nombre_lower.endswith(p):
            return p
        if p.lower() in nombre_lower:
            return p
    return None


@dataclass
class EstadoArchivo:
    mtime_ns: int
    tamano: int


class EmisorEventos:
    def __init__(self, ruta_db: str):
        self.ruta_db = ruta_db
        self._con = sqlite3.connect(self.ruta_db, timeout=30)
        self._con.execute("PRAGMA journal_mode=WAL;")
        self._con.execute("PRAGMA synchronous=NORMAL;")

    def cerrar(self):
        try:
            self._con.close()
        except Exception:
            pass

    def insertar_evento(
        self,
        tipo: str,
        severidad: str,
        origen: str,
        ruta: Optional[str],
        resumen: str,
        detalle_json: Optional[dict] = None,
    ) -> None:
        ts = ahora_utc_iso()
        detalle_txt = json.dumps(detalle_json, ensure_ascii=False) if detalle_json is not None else None
        self._con.execute(
            """
            INSERT INTO eventos(ts, tipo, severidad, origen, ruta, resumen, detalle_json)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (ts, tipo, severidad, origen, ruta, resumen, detalle_txt),
        )
        self._con.commit()


def iterar_archivos(
    incluir: List[str],
    excluir_subrutas: Set[str],
) -> Iterable[Path]:
    for base in incluir:
        base_p = Path(base)
        if not base_p.exists():
            continue
        for raiz, dirs, files in os.walk(base, topdown=True):
            raiz_p = Path(raiz)

            # podar dirs excluidos (por nombre de componente)
            dirs[:] = [d for d in dirs if d not in excluir_subrutas]

            if ruta_tiene_componente(raiz_p, excluir_subrutas):
                continue

            for fn in files:
                yield raiz_p / fn


def filtrar_por_extension(ruta: Path, extensiones: Set[str]) -> bool:
    return ruta.suffix.lower() in extensiones


def escanear(
    incluir: List[str],
    excluir_subrutas: Set[str],
    extensiones: Set[str],
    patrones_prohibidos: List[str],
    estado_prev: Dict[str, EstadoArchivo],
    emisor: EmisorEventos,
    origen: str,
) -> Dict[str, EstadoArchivo]:
    estado_nuevo: Dict[str, EstadoArchivo] = {}

    vistos: Set[str] = set()
    for ruta in iterar_archivos(incluir, excluir_subrutas):
        try:
            ruta_resuelta = ruta.resolve()
        except Exception:
            continue

        ruta_str = str(ruta_resuelta)
        vistos.add(ruta_str)

        nombre = ruta_resuelta.name
        patron = coincide_patron_prohibido(nombre, patrones_prohibidos)
        if patron and not es_bajo_backups(ruta_resuelta):
            emisor.insertar_evento(
                tipo="regla_nombre_prohibido",
                severidad="CRITICAL",
                origen=origen,
                ruta=ruta_str,
                resumen=f"Nombre prohibido detectado fuera de backups/: {nombre}",
                detalle_json={"patron": patron, "archivo": nombre},
            )
            # igual seguimos, pero no forzamos acciones

        if not filtrar_por_extension(ruta_resuelta, extensiones):
            continue

        try:
            st = ruta_resuelta.stat()
        except FileNotFoundError:
            continue
        except PermissionError:
            continue

        actual = EstadoArchivo(mtime_ns=int(st.st_mtime_ns), tamano=int(st.st_size))
        estado_nuevo[ruta_str] = actual

        prev = estado_prev.get(ruta_str)
        if prev is None:
            emisor.insertar_evento(
                tipo="archivo_creado",
                severidad="INFO",
                origen=origen,
                ruta=ruta_str,
                resumen="Archivo detectado (nuevo)",
                detalle_json={"tamano": actual.tamano},
            )
        else:
            if actual.mtime_ns != prev.mtime_ns or actual.tamano != prev.tamano:
                emisor.insertar_evento(
                    tipo="archivo_modificado",
                    severidad="INFO",
                    origen=origen,
                    ruta=ruta_str,
                    resumen="Archivo detectado (modificado)",
                    detalle_json={"tamano": actual.tamano},
                )

    # eliminaciones (solo para los que antes estaban y ya no aparecen)
    for ruta_str in list(estado_prev.keys()):
        if ruta_str not in vistos:
            emisor.insertar_evento(
                tipo="archivo_eliminado",
                severidad="INFO",
                origen=origen,
                ruta=ruta_str,
                resumen="Archivo ya no existe (eliminado o movido)",
                detalle_json=None,
            )

    return estado_nuevo


def main() -> int:
    ap = argparse.ArgumentParser(description="Vigilante de archivos (MONSTRUO)")
    ap.add_argument("--config", default="/srv/monstruo_dev/ops/guardian/configuracion_guardian.json")
    ap.add_argument("--intervalo", type=float, default=2.0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    cfg = cargar_configuracion(args.config)

    incluir = cfg["vigilante_archivos"]["incluir"]
    excluir_subrutas = set(cfg["vigilante_archivos"]["excluir_subrutas"])
    extensiones = set([e.lower() for e in cfg["vigilante_archivos"]["extensiones_interes"]])
    patrones_prohibidos = cfg["vigilante_archivos"]["patrones_prohibidos"]

    ruta_db = cfg["rutas"]["bd_eventos"]
    origen = "vigilante_archivos"

    emisor = EmisorEventos(ruta_db)
    estado_prev: Dict[str, EstadoArchivo] = {}

    try:
        if args.once:
            _ = escanear(incluir, excluir_subrutas, extensiones, patrones_prohibidos, estado_prev, emisor, origen)
            return 0

        while not DETENER:
            estado_prev = escanear(incluir, excluir_subrutas, extensiones, patrones_prohibidos, estado_prev, emisor, origen)
            time.sleep(max(0.2, args.intervalo))
    finally:
        emisor.cerrar()

    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _manejar_senal)
    signal.signal(signal.SIGTERM, _manejar_senal)
    raise SystemExit(main())
