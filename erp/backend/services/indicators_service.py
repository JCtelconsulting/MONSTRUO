import logging
import requests
import time
from typing import Optional
from datetime import date, datetime
from plataforma.core import db as core_db

logger = logging.getLogger(__name__)

# Cache simple en memoria para evitar llamadas excesivas
_uf_cache = {"value": None, "timestamp": 0}
CACHE_TTL = 3600 * 4  # 4 horas
_uf_by_year_cache = {}  # year -> {"values": {YYYY-MM-DD: float}, "timestamp": float}
YEAR_CACHE_TTL = 3600 * 24  # 24 horas


def _get_last_uf_from_db() -> Optional[float]:
    try:
        conn = core_db.get_conn()
        try:
            row = conn.execute(
                "SELECT uf_value FROM uf_rates ORDER BY uf_date DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return float(row["uf_value"] or 0) or None
        finally:
            conn.close()
    except Exception:
        return None


def _get_uf_for_date_from_db(d: date) -> Optional[float]:
    try:
        conn = core_db.get_conn()
        try:
            row = conn.execute(
                "SELECT uf_value FROM uf_rates WHERE uf_date = ? LIMIT 1",
                (d.isoformat(),),
            ).fetchone()
            if not row:
                return None
            return float(row["uf_value"] or 0) or None
        finally:
            conn.close()
    except Exception:
        return None


def _save_uf_to_db(d: date, value: float, source: str = "mindicador") -> None:
    try:
        conn = core_db.get_conn()
        try:
            now = core_db.now_utc_iso()
            conn.execute(
                """
                INSERT INTO uf_rates (uf_date, uf_value, source, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(uf_date) DO UPDATE SET
                  uf_value=excluded.uf_value,
                  source=excluded.source,
                  fetched_at=excluded.fetched_at
                """,
                (d.isoformat(), float(value), (source or "mindicador"), now),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # UF es un dato auxiliar; no debe botar la app si no se puede persistir.
        return


def get_uf_value() -> Optional[float]:
    """
    Obtiene el valor de la UF del día desde Mindicador.cl
    Retorna None si hay error.
    """
    global _uf_cache
    now = time.time()

    # Retornar desde cache si es válido
    if _uf_cache["value"] and (now - _uf_cache["timestamp"] < CACHE_TTL):
        return _uf_cache["value"]

    # Warmup: si recién partió el proceso y no hay cache en memoria,
    # usar último valor persistido para evitar 503 cuando Mindicador falla.
    if not _uf_cache["value"]:
        last = _get_last_uf_from_db()
        if last:
            _uf_cache["value"] = last
            _uf_cache["timestamp"] = now

    try:
        # Mindicador es una API gratuita y estable para Chile
        resp = requests.get("https://mindicador.cl/api/uf", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            # La serie viene ordenada por fecha descendente (hoy primero)
            if "serie" in data and len(data["serie"]) > 0:
                value = float(data["serie"][0]["valor"])
                _uf_cache["value"] = value
                _uf_cache["timestamp"] = now
                _save_uf_to_db(date.today(), value, source="mindicador")
                return value
    except Exception as e:
        logger.error("Error fetching UF: %s", e)

    return _uf_cache["value"]  # Retornar viejo si falló el nuevo


def _parse_uf_series_to_map(payload: dict) -> dict:
    values = {}
    serie = payload.get("serie") or []
    for it in serie:
        try:
            dt = it.get("fecha")
            val = it.get("valor")
            if dt is None or val is None:
                continue
            # Mindicador suele venir en ISO Z, ej: 2024-06-03T04:00:00.000Z
            d = datetime.fromisoformat(str(dt).replace("Z", "+00:00")).date()
            values[d.isoformat()] = float(val)
        except Exception:
            continue
    return values


def get_uf_value_for_date(d: date) -> Optional[float]:
    """
    Obtiene el valor UF para una fecha específica.
    Usa cache por año para evitar llamadas repetidas.
    """
    if not isinstance(d, date):
        return None

    # 0) DB cache (persistente)
    cached = _get_uf_for_date_from_db(d)
    if cached:
        return cached

    year = d.year
    now = time.time()
    entry = _uf_by_year_cache.get(year)
    if entry and (now - entry["timestamp"] < YEAR_CACHE_TTL):
        return entry["values"].get(d.isoformat())

    # 1) Intento rápido: endpoint base trae una ventana de fechas reciente
    try:
        resp = requests.get("https://mindicador.cl/api/uf", timeout=8)
        if resp.status_code == 200:
            values = _parse_uf_series_to_map(resp.json())
            if d.isoformat() in values:
                _uf_by_year_cache[year] = {"values": values, "timestamp": now}
                _save_uf_to_db(d, values[d.isoformat()], source="mindicador")
                return values[d.isoformat()]
    except Exception:
        pass

    # 2) Fallback: endpoint anual
    try:
        resp = requests.get(f"https://mindicador.cl/api/uf/{year}", timeout=12)
        if resp.status_code == 200:
            values = _parse_uf_series_to_map(resp.json())
            _uf_by_year_cache[year] = {"values": values, "timestamp": now}
            val = values.get(d.isoformat())
            if val:
                _save_uf_to_db(d, val, source="mindicador")
            return val
    except Exception as e:
        logger.error("Error fetching UF for date %s: %s", d, e)

    return None
