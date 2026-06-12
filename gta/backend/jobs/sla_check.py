"""Job de evaluación de SLA del GTA.

Cada 10 minutos:
- Recorre las tareas activas
- Calcula % de SLA consumido (descontando tiempo pausado por ayudas)
- Si cruza 70% → DM al asignado
- Si cruza 85% → DM al asignado + DM al jefe
- Si llega a 100% → marca tarea como vencida + DM al asignado + DM al jefe

last_sla_warn_pct evita notificaciones duplicadas en cada corrida.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from plataforma.core import db, jobs_engine, notifications, google_chat
from plataforma.core.config import settings as app_settings
from gta.backend.services import flujos as flujos_service

logger = logging.getLogger(__name__)

JOB_TYPE = "GTA_SLA_CHECK"
INTERVAL_MIN = 10


def _next_run_iso(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=max(1, int(minutes or 1)))).isoformat()


async def _schedule_next(minutes: int = INTERVAL_MIN) -> None:
    await jobs_engine.enqueue_unique_job(
        JOB_TYPE,
        {"recurring": True},
        max_retries=1,
        next_run_at=_next_run_iso(minutes),
        update_existing_next_run=False,
    )


def _settings_get(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM gta.settings WHERE key = %s", (key,)).fetchone()
    return str(row["value"]) if row else default


def _notify(conn, *, user_id: str, mensaje: str, severity: str = "INFO",
            chat_text: Optional[str] = None) -> None:
    """Inserta notificación in-app y opcionalmente envía DM por Google Chat."""
    if not user_id:
        return
    notifications.send_notification(user_id=user_id, message=mensaje, severity=severity)

    bot_token = str(getattr(app_settings, "GOOGLE_CHAT_BOT_TOKEN", "") or "").strip()
    if bot_token and chat_text:
        try:
            google_chat.send_dm(bot_token, user_id, chat_text)
        except Exception as e:
            logger.warning("[GTA_SLA] Google Chat DM falló para %s: %s", user_id, e)


def _check_tareas() -> dict:
    """Evalúa todas las tareas activas y dispara notificaciones según umbrales."""
    warn_pct = 70
    crit_pct = 85

    conn = db.get_conn()
    try:
        warn_pct = int(_settings_get(conn, "sla_warn_pct", "70") or "70")
        crit_pct = int(_settings_get(conn, "sla_critical_pct", "85") or "85")
        jefe = _settings_get(conn, "jefe_username", "")

        # Tareas con SLA activo (corriendo, no pausadas, no completadas)
        rows = conn.execute(
            """SELECT t.*, f.titulo AS flujo_titulo, f.iniciado_por
               FROM gta.flujo_tareas t
               JOIN gta.flujos f ON f.id = t.flujo_id
               WHERE t.estado IN ('lista', 'en_progreso', 'por_validar')
                 AND t.sla_horas > 0
                 AND t.inicio_at IS NOT NULL
                 AND t.sla_pause_started_at IS NULL"""
        ).fetchall()

        evaluated = 0
        notif_warn = 0
        notif_crit = 0
        notif_vencida = 0

        for row in rows:
            tarea = dict(row)
            sla = flujos_service.calcular_sla_pct(tarea)
            pct = int(sla["pct"])
            last_warn = int(tarea.get("last_sla_warn_pct") or 0)
            evaluated += 1

            asignado = str(tarea.get("asignado_a") or "")
            titulo_t = str(tarea.get("titulo") or "tarea")
            flujo_titulo = str(tarea.get("flujo_titulo") or "")
            tarea_id = int(tarea["id"])
            flujo_id = int(tarea["flujo_id"])

            new_warn_level = last_warn

            # 100% → vencida
            if pct >= 100 and last_warn < 100:
                conn.execute(
                    """UPDATE gta.flujo_tareas
                       SET estado = 'vencida', last_sla_warn_pct = 100, updated_at = CURRENT_TIMESTAMP
                       WHERE id = %s""",
                    (tarea_id,),
                )
                flujos_service.log_evento(
                    conn, flujo_id, "sla_vencida", "system", tarea_id=tarea_id,
                    mensaje=f"SLA vencido: {titulo_t} ({pct}%)",
                )
                msg = f"⛔ SLA VENCIDO en '{flujo_titulo}': la tarea '{titulo_t}' superó el 100% del tiempo asignado"
                _notify(conn, user_id=asignado, mensaje=msg, severity="CRITICAL", chat_text=msg)
                if jefe and jefe != asignado:
                    _notify(conn, user_id=jefe, mensaje=msg, severity="CRITICAL", chat_text=msg)
                new_warn_level = 100
                notif_vencida += 1

            # 85% crítico
            elif pct >= crit_pct and last_warn < crit_pct:
                msg = f"🟠 SLA CRÍTICO en '{flujo_titulo}': '{titulo_t}' al {pct}% del tiempo"
                _notify(conn, user_id=asignado, mensaje=msg, severity="WARNING", chat_text=msg)
                if jefe and jefe != asignado:
                    _notify(conn, user_id=jefe, mensaje=msg, severity="WARNING", chat_text=msg)
                flujos_service.log_evento(
                    conn, flujo_id, "sla_warn_85", "system", tarea_id=tarea_id,
                    mensaje=f"SLA al {pct}%",
                )
                new_warn_level = crit_pct
                notif_crit += 1

            # 70% advertencia
            elif pct >= warn_pct and last_warn < warn_pct:
                msg = f"🟡 SLA al {pct}% en '{flujo_titulo}': '{titulo_t}' — no te quedes corto de tiempo"
                _notify(conn, user_id=asignado, mensaje=msg, severity="INFO", chat_text=msg)
                flujos_service.log_evento(
                    conn, flujo_id, "sla_warn_70", "system", tarea_id=tarea_id,
                    mensaje=f"SLA al {pct}%",
                )
                new_warn_level = warn_pct
                notif_warn += 1

            # Persistir el nuevo nivel solo si cambió
            if new_warn_level != last_warn and new_warn_level not in (0, 100):
                # caso 100 ya se actualizó arriba; caso 0 es estado inicial sin notif
                conn.execute(
                    "UPDATE gta.flujo_tareas SET last_sla_warn_pct = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (new_warn_level, tarea_id),
                )

        conn.commit()
        return {
            "evaluated": evaluated,
            "notif_warn_70": notif_warn,
            "notif_crit_85": notif_crit,
            "notif_vencidas": notif_vencida,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def gta_sla_check(payload: dict = None):
    """Job handler: ejecuta la evaluación y se reenqueue cada N minutos."""
    payload = payload or {}
    try:
        result = _check_tareas()
        logger.info(
            "[GTA_SLA] evaluadas=%d warn70=%d crit85=%d vencidas=%d",
            result["evaluated"], result["notif_warn_70"],
            result["notif_crit_85"], result["notif_vencidas"],
        )
    except Exception as e:
        logger.exception("[GTA_SLA] error en evaluación: %s", e)

    if payload.get("recurring", True):
        await _schedule_next(INTERVAL_MIN)
