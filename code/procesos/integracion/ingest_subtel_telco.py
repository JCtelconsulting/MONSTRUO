#!/usr/bin/env python3
"""Ingesta incremental de empresas telco desde datos abiertos SUBTEL.

Fuentes:
- Autorizaciones de Estaciones Base (SUBTEL, datos.gob.cl)

No hace scraping. Descarga archivos oficiales y completa campos vacios
con match por nombre de empresa (normalizado).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import time
import unicodedata
import urllib.request
from collections import Counter
from typing import Dict, Iterable, Optional

import pandas as pd

DEFAULT_INPUT = "/srv/monstruo_dev/data/files/BD Telecomunicaciones.xlsx"
DEFAULT_OUTPUT = "/srv/monstruo_dev/data/files/BD Telecomunicaciones.enriquecido.xlsx"
DEFAULT_CACHE_DIR = "/srv/monstruo_dev/data/files/sources"
DEFAULT_LOG = "/srv/monstruo_dev/data/logs/telco_ingest.log"
DEFAULT_CONFIG = "/srv/monstruo_dev/data/files/telco_ingest_sources.json"

SUBTEL_ANTENNAS_URL = (
    "https://datos.gob.cl/uploads/recursos/"
    "Copia%20de%20Autorizaciones_de_Estaciones%20Base_a%20nivel%20Nacional_Setiembre2015.xlsx"
)

LEGAL_SUFFIXES = {
    "spa",
    "s.a.",
    "sa",
    "ltda",
    "eirl",
    "s.a",
    "s.a.p.i",
    "s.a.p.i.",
}


def setup_logger(path: str) -> logging.Logger:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    logger = logging.getLogger("telco_ingest")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(path)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def load_config(path: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def download_file(url: str, dest_path: str, refresh: bool = False) -> str:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path) and not refresh:
        return dest_path
    tmp_path = dest_path + ".tmp"
    with urllib.request.urlopen(url) as resp, open(tmp_path, "wb") as f:
        f.write(resp.read())
    os.replace(tmp_path, dest_path)
    return dest_path


def normalize_name(value: str) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\b(s\s*a\.?|s\.a\.?|s\s*p\s*a\.?|s\.p\.a\.?|ltda\.?|eirl\.?|spa)\b", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    parts = [p for p in text.split() if p and p not in LEGAL_SUFFIXES]
    return " ".join(parts)


def pick_mode(values: Iterable[str]) -> str:
    clean = [v for v in values if isinstance(v, str) and v.strip()]
    if not clean:
        return ""
    counts = Counter(clean)
    return counts.most_common(1)[0][0]


def build_subtel_antenna_index(path: str) -> Dict[str, dict]:
    df = pd.read_excel(path)
    df = df.fillna("")

    grouped = {}
    for _, row in df.iterrows():
        empresa = str(row.get("Empresa", "")).strip()
        if not empresa:
            continue
        key = normalize_name(empresa)
        if not key:
            continue
        grouped.setdefault(key, []).append(row)

    index = {}
    for key, rows in grouped.items():
        direcciones = [r.get("Dirección", "") for r in rows]
        comunas = [r.get("Comuna", "") for r in rows]
        regiones = [r.get("Región", "") for r in rows]
        servicios = [r.get("Servicio", "") for r in rows]
        tipos = [r.get("Tipo Servicio", "") for r in rows]
        sistemas = [r.get("Sistema", "") for r in rows]

        linea_parts = [
            p for p in (pick_mode(servicios), pick_mode(tipos), pick_mode(sistemas)) if p
        ]
        linea = " / ".join(linea_parts)
        if len(linea) > 140:
            linea = linea[:137] + "..."

        index[key] = {
            "direccion": pick_mode(direcciones),
            "ciudad": pick_mode(comunas),
            "region": pick_mode(regiones),
            "linea": linea,
        }
    return index


def fill_row(row: pd.Series, source_index: Dict[str, dict]) -> bool:
    def is_blank(value: object) -> bool:
        if value is None:
            return True
        try:
            if pd.isna(value):
                return True
        except Exception:
            pass
        return str(value).strip() == ""

    nombre = str(row.get("Nombre Empresa", "")).strip()
    if not nombre:
        return False
    key = normalize_name(nombre)
    if not key or key not in source_index:
        return False

    data = source_index[key]
    changed = False

    if is_blank(row.get("Dirección", "")) and data.get("direccion"):
        row["Dirección"] = data["direccion"]
        changed = True
    if is_blank(row.get("Ciudad", "")) and data.get("ciudad"):
        row["Ciudad"] = data["ciudad"]
        changed = True
    if is_blank(row.get("Línea de Negocio", "")) and data.get("linea"):
        row["Línea de Negocio"] = data["linea"]
        changed = True

    return changed


def process_excel(
    input_path: str,
    output_path: str,
    source_index: Dict[str, dict],
    max_rows: int,
    logger: logging.Logger,
) -> int:
    df = pd.read_excel(input_path)
    for col in ("Dirección", "Ciudad", "Línea de Negocio"):
        if col in df.columns:
            df[col] = df[col].astype("object")
    updated = 0

    for idx in df.index:
        if updated >= max_rows:
            break
        row = df.loc[idx]
        if fill_row(row, source_index):
            df.loc[idx] = row
            updated += 1

    if updated or (output_path != input_path and not os.path.exists(output_path)):
        df.to_excel(output_path, index=False)
    return updated


def backup_file(path: str) -> str:
    if not os.path.exists(path):
        return ""
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = "/srv/monstruo_dev/data/backups/telco"
    os.makedirs(backup_dir, exist_ok=True)
    dest = os.path.join(backup_dir, f"BD_Telecomunicaciones_{ts}.xlsx")
    with open(path, "rb") as src, open(dest, "wb") as dst:
        dst.write(src.read())
    return dest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingesta telco SUBTEL -> Excel")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-rows", type=int, default=1)
    parser.add_argument("--sleep", type=int, default=30)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--inplace", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = setup_logger(DEFAULT_LOG)

    config = load_config(args.config)
    subtel_url = config.get("subtel_antennas_url", SUBTEL_ANTENNAS_URL)
    cache_path = os.path.join(args.cache_dir, "subtel_antennas.xlsx")

    try:
        download_file(subtel_url, cache_path, refresh=args.refresh)
    except Exception as exc:
        logger.error("No se pudo descargar fuente SUBTEL: %s", exc)
        raise

    source_index = build_subtel_antenna_index(cache_path)
    if not source_index:
        logger.warning("Indice SUBTEL vacio; no se actualizara nada.")

    input_path = args.input
    output_path = input_path if args.inplace else args.output

    if args.inplace:
        backup_path = backup_file(input_path)
        if backup_path:
            logger.info("Backup creado: %s", backup_path)

    logger.info("Inicio ingest: input=%s output=%s max_rows=%s loop=%s", input_path, output_path, args.max_rows, args.loop)

    while True:
        updated = process_excel(input_path, output_path, source_index, args.max_rows, logger)
        logger.info("Filas actualizadas: %s", updated)
        if not args.loop:
            break
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
