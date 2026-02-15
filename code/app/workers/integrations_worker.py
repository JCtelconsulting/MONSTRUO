import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest

from app.core import db, tickets_service
from app.core.config import settings

logger = logging.getLogger(__name__)


def _adapter_mode(channel: str) -> str:
    if channel == "whatsapp":
        return tickets_service.normalize_adapter_mode(
            getattr(settings, "WHATSAPP_ADAPTER_MODE", "disabled"), "disabled"
        )
    if channel == "3cx":
        return tickets_service.normalize_adapter_mode(
            getattr(settings, "THREECX_ADAPTER_MODE", "disabled"), "disabled"
        )
    return "disabled"


def _adapter_timeout_seconds(channel: str) -> int:
    raw = (
        getattr(settings, "WHATSAPP_TIMEOUT_SECONDS", 10)
        if channel == "whatsapp"
        else getattr(settings, "THREECX_TIMEOUT_SECONDS", 10)
    )
    try:
        return max(1, min(int(raw), 120))
    except Exception:
        return 10


def _adapter_base_url(channel: str) -> str:
    if channel == "whatsapp":
        return str(getattr(settings, "WHATSAPP_BASE_URL", "") or "").strip()
    if channel == "3cx":
        return str(getattr(settings, "THREECX_BASE_URL", "") or "").strip()
    return ""


def _adapter_auth_token(channel: str) -> str:
    if channel == "whatsapp":
        return str(getattr(settings, "WHATSAPP_AUTH_TOKEN", "") or "").strip()
    if channel == "3cx":
        return str(getattr(settings, "THREECX_AUTH_TOKEN", "") or "").strip()
    return ""


def _channels_enabled() -> bool:
    return bool(getattr(settings, "CHANNELS_ENABLED", False))


def _http_post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout_seconds: int,
) -> Tuple[int, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(url=url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        if value:
            req.add_header(key, value)
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as resp:
            status = int(getattr(resp, "status", 0) or 0)
            raw = resp.read().decode("utf-8", errors="replace")
            return status, raw
    except urlerror.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(e)
        return int(e.code or 500), raw


def _extract_provider_ref(raw: str) -> str:
    try:
        parsed = json.loads(raw or "{}")
    except Exception:
        return ""
    for key in ("id", "message_id", "call_id", "reference", "provider_ref"):
        value = parsed.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _load_notification_context(conn, notification_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """SELECT tn.*,
                  t.codigo AS ticket_codigo,
                  t.titulo AS ticket_titulo,
                  u.phone_number AS user_phone
           FROM ticket_notifications tn
           JOIN tickets t ON t.id = tn.ticket_id
           LEFT JOIN users u ON u.username = tn.user_id
           WHERE tn.id = ?""",
        (notification_id,),
    ).fetchone()
    return dict(row) if row else None


def _acquire_dispatching_state(conn, notification_id: int) -> Optional[Dict[str, Any]]:
    now = db.now_utc_iso()
    row = conn.execute(
        """UPDATE ticket_notifications
           SET status = 'dispatching',
               locked_at = ?,
               updated_at = ?
           WHERE id = ?
             AND status = 'pending'
           RETURNING *""",
        (now, now, notification_id),
    ).fetchone()
    return dict(row) if row else None


def _retry_policy(max_attempts_raw: Any, attempt_count_raw: Any) -> Tuple[int, int, int]:
    try:
        max_attempts = int(max_attempts_raw)
    except Exception:
        max_attempts = 0
    if max_attempts <= 0:
        max_attempts = tickets_service.CHANNELS_MAX_ATTEMPTS
    max_attempts = max(1, min(max_attempts, 20))
    try:
        attempt_count = int(attempt_count_raw)
    except Exception:
        attempt_count = 0
    attempt_count = max(0, attempt_count)
    next_attempt = attempt_count + 1
    return max_attempts, attempt_count, next_attempt


def _apply_success(conn, notif: Dict[str, Any], provider: str, provider_ref: str) -> None:
    now = db.now_utc_iso()
    conn.execute(
        """UPDATE ticket_notifications
           SET status = 'sent',
               provider = ?,
               provider_ref = ?,
               sent_at = ?,
               last_error = '',
               error = '',
               locked_at = NULL,
               next_retry_at = NULL,
               updated_at = ?
           WHERE id = ?""",
        (provider, provider_ref, now, now, int(notif["id"])),
    )


def _apply_failure(
    conn,
    notif: Dict[str, Any],
    *,
    provider: str,
    error_message: str,
    retryable: bool,
) -> Tuple[str, Optional[str], int]:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    max_attempts, _, next_attempt = _retry_policy(
        notif.get("max_attempts"),
        notif.get("attempt_count"),
    )
    final_status = "failed"
    next_retry_at: Optional[str] = None

    if retryable and next_attempt < max_attempts:
        delay = tickets_service._channel_retry_delay_seconds(next_attempt)
        next_retry_at = (now_dt + timedelta(seconds=delay)).isoformat()
        final_status = "pending"

    conn.execute(
        """UPDATE ticket_notifications
           SET status = ?,
               provider = ?,
               attempt_count = ?,
               last_error = ?,
               error = ?,
               next_retry_at = ?,
               locked_at = NULL,
               updated_at = ?
           WHERE id = ?""",
        (
            final_status,
            provider,
            next_attempt,
            error_message[:2000],
            error_message[:2000],
            next_retry_at,
            now,
            int(notif["id"]),
        ),
    )
    return final_status, next_retry_at, next_attempt


def _build_channel_message(notif: Dict[str, Any]) -> str:
    code = str(notif.get("ticket_codigo") or notif.get("codigo") or f"#{notif.get('ticket_id')}")
    title = str(notif.get("ticket_titulo") or notif.get("titulo") or "").strip()
    if title:
        return f"Ticket {code}: {title} requiere tu atención."
    return f"Ticket {code} requiere tu atención."


def _run_adapter_sync(
    channel: str,
    notif: Dict[str, Any],
    mode: str,
) -> Dict[str, Any]:
    notif_id = int(notif["id"])
    ticket_id = int(notif["ticket_id"])
    phone = str(notif.get("user_phone") or "").strip()
    if not phone:
        return {
            "ok": False,
            "provider_ref": "",
            "http_status": None,
            "error": "Usuario sin phone_number para notificación de canal",
            "retryable": False,
            "latency_ms": 0,
        }

    if not _channels_enabled():
        return {
            "ok": False,
            "provider_ref": "",
            "http_status": None,
            "error": "CHANNELS_ENABLED=false",
            "retryable": False,
            "latency_ms": 0,
        }

    if mode == "disabled":
        return {
            "ok": False,
            "provider_ref": "",
            "http_status": None,
            "error": f"adapter {channel} disabled",
            "retryable": False,
            "latency_ms": 0,
        }

    if mode == "dry_run":
        ref = f"dryrun:{channel}:{notif_id}:{int(time.time() * 1000)}"
        logger.info("[CHANNEL_DRY_RUN] %s notif=%s ticket=%s phone=%s", channel, notif_id, ticket_id, phone)
        return {
            "ok": True,
            "provider_ref": ref,
            "http_status": 200,
            "error": "",
            "retryable": False,
            "latency_ms": 0,
        }

    base_url = _adapter_base_url(channel)
    auth_token = _adapter_auth_token(channel)
    if not base_url or not auth_token:
        return {
            "ok": False,
            "provider_ref": "",
            "http_status": None,
            "error": f"adapter {channel} live sin credenciales (base_url/token)",
            "retryable": True,
            "latency_ms": 0,
        }

    path = "/messages" if channel == "whatsapp" else "/calls"
    url = f"{base_url.rstrip('/')}{path}"
    message = _build_channel_message(notif)
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Idempotency-Key": f"notification-{notif_id}",
        "X-Ticket-Id": str(ticket_id),
    }
    payload = {
        "notification_id": notif_id,
        "ticket_id": ticket_id,
        "ticket_code": str(notif.get("ticket_codigo") or ""),
        "to": phone,
        "message": message,
        "channel": channel,
    }
    timeout_seconds = _adapter_timeout_seconds(channel)

    start = time.perf_counter()
    try:
        status, raw = _http_post_json(url, payload, headers, timeout_seconds)
    except Exception as e:
        elapsed = int((time.perf_counter() - start) * 1000)
        return {
            "ok": False,
            "provider_ref": "",
            "http_status": None,
            "error": str(e),
            "retryable": True,
            "latency_ms": elapsed,
        }

    elapsed = int((time.perf_counter() - start) * 1000)
    provider_ref = _extract_provider_ref(raw)
    if not provider_ref and 200 <= status < 300:
        provider_ref = f"{channel}:{notif_id}:{int(time.time() * 1000)}"

    if 200 <= status < 300:
        return {
            "ok": True,
            "provider_ref": provider_ref,
            "http_status": status,
            "error": "",
            "retryable": False,
            "latency_ms": elapsed,
        }

    retryable = status in {408, 409, 425, 429, 500, 502, 503, 504}
    return {
        "ok": False,
        "provider_ref": provider_ref,
        "http_status": status,
        "error": f"HTTP {status}: {raw[:1000]}",
        "retryable": retryable,
        "latency_ms": elapsed,
    }


async def _dispatch_notification(channel: str, payload: Dict[str, Any]) -> None:
    notif_id = int(payload.get("notification_id") or 0)
    if notif_id <= 0:
        logger.warning("[CHANNEL] payload inválido para %s: %s", channel, payload)
        return

    provider = tickets_service._channel_provider_name(channel)
    mode = _adapter_mode(channel)
    conn = db.get_conn()
    notif: Optional[Dict[str, Any]] = None
    try:
        notif = _load_notification_context(conn, notif_id)
        if not notif:
            logger.warning("[CHANNEL] notification_id=%s no existe", notif_id)
            return

        notif_channel = tickets_service.normalize_channel_name(notif.get("channel"))
        if notif_channel != channel:
            logger.warning(
                "[CHANNEL] channel mismatch notification_id=%s expected=%s got=%s",
                notif_id,
                channel,
                notif_channel,
            )
            return

        status_now = tickets_service.normalize_notification_status(notif.get("status"))
        if status_now in {"sent", "failed", "cancelled"}:
            return

        if status_now != "dispatching":
            acquired = _acquire_dispatching_state(conn, notif_id)
            if not acquired:
                conn.commit()
                return
            notif = _load_notification_context(conn, notif_id) or acquired

        max_attempts, _, next_attempt = _retry_policy(
            notif.get("max_attempts"),
            notif.get("attempt_count"),
        )
        if next_attempt > max_attempts:
            _apply_failure(
                conn,
                notif,
                provider=provider,
                error_message="Max attempts alcanzado",
                retryable=False,
            )
            conn.commit()
            tickets_service.log_notification_attempt(
                notif_id,
                attempt_no=next_attempt,
                attempt_type="dispatch",
                channel=channel,
                provider=provider,
                adapter_mode=mode,
                status="error_final",
                provider_ref="",
                error="Max attempts alcanzado",
            )
            return

        result = await asyncio.to_thread(_run_adapter_sync, channel, notif, mode)
        if result.get("ok"):
            _apply_success(conn, notif, provider, str(result.get("provider_ref") or ""))
            conn.commit()
            tickets_service.log_notification_attempt(
                notif_id,
                attempt_no=next_attempt,
                attempt_type="dispatch",
                channel=channel,
                provider=provider,
                adapter_mode=mode,
                status="ok",
                provider_ref=str(result.get("provider_ref") or ""),
                http_status=result.get("http_status"),
                latency_ms=result.get("latency_ms"),
            )
            return

        final_status, _, saved_attempt = _apply_failure(
            conn,
            notif,
            provider=provider,
            error_message=str(result.get("error") or "Error desconocido en adapter"),
            retryable=bool(result.get("retryable")),
        )
        conn.commit()
        tickets_service.log_notification_attempt(
            notif_id,
            attempt_no=saved_attempt,
            attempt_type="dispatch",
            channel=channel,
            provider=provider,
            adapter_mode=mode,
            status="error_retry" if final_status == "pending" else "error_final",
            provider_ref=str(result.get("provider_ref") or ""),
            http_status=result.get("http_status"),
            latency_ms=result.get("latency_ms"),
            error=str(result.get("error") or ""),
        )
    except Exception as e:
        logger.exception("[CHANNEL] error inesperado notification_id=%s channel=%s", notif_id, channel)
        try:
            if notif:
                _apply_failure(
                    conn,
                    notif,
                    provider=provider,
                    error_message=str(e),
                    retryable=True,
                )
                conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


async def send_whatsapp_notification(payload: dict):
    await _dispatch_notification("whatsapp", payload or {})


async def send_3cx_call(payload: dict):
    await _dispatch_notification("3cx", payload or {})
