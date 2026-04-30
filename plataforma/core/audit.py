from __future__ import annotations

import hashlib
import json
import logging

from plataforma.core import db

logger = logging.getLogger(__name__)

CHAIN_ALGO = "sha256"
CHAIN_VERSION = 1


def _stable_json(data: dict) -> str:
    return json.dumps(data or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_chain_hash(prev_hash: str, payload: dict) -> str:
    raw = f"{prev_hash or ''}|{_stable_json(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def log_audit(
    actor: str,
    action: str,
    target: str = "",
    ip: str = "",
    severity: str = "info",
    metadata: dict = None,
) -> None:
    try:
        conn = db.get_conn()
        ts = db.now_utc_iso()
        meta_str = _stable_json(metadata or {})
        prev_row = conn.execute(
            "SELECT chain_hash FROM audit_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_hash = (prev_row["chain_hash"] if prev_row else "") or ""
        payload = {
            "timestamp": ts,
            "actor": actor or "",
            "action": action or "",
            "target": target or "",
            "ip_address": ip or "",
            "severity": severity or "info",
            "metadata_json": meta_str,
        }
        chain_hash = _build_chain_hash(prev_hash, payload)
        conn.execute(
            """INSERT INTO audit_logs
               (timestamp, actor, action, target, ip_address, severity, metadata_json,
                chain_prev_hash, chain_hash, chain_algo, chain_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ts, actor, action, target, ip, severity, meta_str,
                prev_hash, chain_hash, CHAIN_ALGO, CHAIN_VERSION,
            ),
        )
        conn.commit()
    except Exception as e:
        logger.error("AUDIT FAIL: %s", e)
    finally:
        conn.close()
