from __future__ import annotations

import logging
from datetime import datetime, timezone

from plataforma.core import db

logger = logging.getLogger(__name__)


def send_notification(user_id: str, message: str, severity: str = "INFO") -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        conn = db.get_conn()
        try:
            conn.execute(
                """INSERT INTO core.sys_notifications (user_id, message, severity, created_at)
                   VALUES (%s, %s, %s, %s)""",
                (str(user_id or ""), str(message or ""), str(severity or "INFO"), timestamp),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.error("Failed to save notification for %s: %s", user_id, e)


def notify_ticket_escalation(ticket_id: int, title: str, assignee_id: str) -> None:
    msg = f"TICKET #{ticket_id} '{title}' ha escalado a CRITICO por SLA."
    target = assignee_id if assignee_id else "OPS_CHANNEL"
    send_notification(target, msg, "CRITICAL")
