from __future__ import annotations

import base64
import email
import html
import imaplib
import logging
import mimetypes
import re
import time
from email.header import decode_header

from plataforma.core import db

logger = logging.getLogger(__name__)

_IMAP_MAX_RETRIES = 3
_IMAP_RETRY_BACKOFF = (2, 5, 10)


def get_imap_config():
    conn = db.get_conn()
    try:
        keys = ["imap_host", "imap_port", "imap_user", "imap_password", "email_polling_interval"]
        placeholders = ", ".join(["%s" for _ in keys])
        query = f"SELECT key, value FROM system_settings WHERE key IN ({placeholders})"
        cursor = conn.execute(query, tuple(keys))
        rows = cursor.fetchall()
        config = {}
        for r in rows:
            if isinstance(r, dict):
                config[r["key"]] = r["value"]
            else:
                config[r[0]] = r[1]
        if not config.get("imap_host"):
            return None
        return config
    finally:
        conn.close()


def clean_html_content(html_content: str) -> str:
    if not html_content:
        return ""
    clean = re.sub(r"<(script|style).*?>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", "\n", clean)
    clean = html.unescape(clean)
    lines = [line.strip() for line in clean.splitlines()]
    return "\n".join(line for line in lines if line)


def _decode_mime_value(raw_value) -> str:
    if not raw_value:
        return ""
    parts = []
    try:
        for part, encoding in decode_header(raw_value):
            if isinstance(part, bytes):
                parts.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                parts.append(str(part))
    except Exception:
        return str(raw_value)
    return "".join(parts).strip()


def _normalize_content_id(raw_value) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    if value.lower().startswith("cid:"):
        value = value[4:]
    return value.strip().strip("<>").strip().lower()


def _preferred_extension(content_type: str) -> str:
    guessed = mimetypes.guess_extension(str(content_type or "").strip().lower()) or ""
    return {".jpe": ".jpg", ".jpeg": ".jpg", ".tiff": ".tif"}.get(guessed.lower(), guessed.lower())


def _fallback_inline_filename(content_type: str, content_id: str, index: int) -> str:
    ext = _preferred_extension(content_type) or ".bin"
    safe_cid = re.sub(r"[^a-z0-9._-]+", "-", str(content_id or "").strip().lower()).strip("-")
    base = safe_cid or f"inline-{index}"
    return f"{base}{ext}"


def _decode_part_payload(part, payload: bytes) -> str:
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except Exception:
        return payload.decode("utf-8", errors="replace")


class EmailProcessor:
    def __init__(self):
        self.config = get_imap_config()
        self.mail: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        if not self.config:
            raise ValueError("No IMAP config found")

        host = self.config["imap_host"]
        port = int(self.config.get("imap_port", 993))
        user = self.config["imap_user"]
        password = self.config["imap_password"]

        last_exc: Exception | None = None
        for attempt in range(_IMAP_MAX_RETRIES):
            try:
                self.mail = imaplib.IMAP4_SSL(host, port, timeout=30)
                self.mail.login(user, password)
                return
            except Exception as e:
                last_exc = e
                wait = _IMAP_RETRY_BACKOFF[min(attempt, len(_IMAP_RETRY_BACKOFF) - 1)]
                logger.warning("[IMAP] Connect attempt %s/%s failed: %s — retrying in %ss", attempt + 1, _IMAP_MAX_RETRIES, e, wait)
                time.sleep(wait)
        raise ConnectionError(f"IMAP connect failed after {_IMAP_MAX_RETRIES} attempts: {last_exc}") from last_exc

    def _ensure_connected(self) -> None:
        try:
            if self.mail is not None:
                self.mail.noop()
                return
        except Exception:
            pass
        logger.info("[IMAP] Connection lost — reconnecting...")
        self.connect()

    def fetch_unread(self) -> list[dict]:
        self._ensure_connected()
        self.mail.select("inbox")
        status, messages = self.mail.search(None, "UNSEEN")
        if status != "OK":
            return []

        email_ids = messages[0].split()
        emails = []
        for e_id in email_ids:
            try:
                res, msg = self.mail.fetch(e_id, "(RFC822)")
                for response in msg:
                    if isinstance(response, tuple):
                        parsed = self.parse_email(email.message_from_bytes(response[1]))
                        emails.append(parsed)
            except Exception as e:
                logger.error("[IMAP] Error fetching email %s: %s", e_id, e)
        return emails

    def select_inbox(self, readonly: bool = False) -> None:
        self._ensure_connected()
        self.mail.select("inbox", readonly=readonly)

    def get_uidnext(self) -> int:
        """UIDNEXT actual del INBOX. Útil para inicializar el cursor sin
        reprocesar historial."""
        self._ensure_connected()
        status, data = self.mail.status("inbox", "(UIDNEXT)")
        if status != "OK" or not data:
            raise RuntimeError(f"IMAP STATUS UIDNEXT failed: {status}")
        raw = data[0] if isinstance(data, list) else data
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        match = re.search(r"UIDNEXT\s+(\d+)", text)
        if not match:
            raise RuntimeError(f"IMAP STATUS UIDNEXT unparseable: {text!r}")
        return int(match.group(1))

    def fetch_new(self, last_uid: int) -> list[dict]:
        """Devuelve correos con UID > last_uid usando BODY.PEEK (no marca Seen).

        El cursor por UID es independiente del flag Seen, así que correos
        marcados como Seen por otro cliente IMAP siguen siendo procesados.
        Cada dict incluye `uid: int` para que el caller pueda marcar Seen
        y avanzar el cursor selectivamente.
        """
        self._ensure_connected()
        self.mail.select("inbox", readonly=False)
        try:
            cursor = int(last_uid)
        except (TypeError, ValueError):
            cursor = 0
        cursor = max(cursor, 0)

        status, messages = self.mail.uid("SEARCH", None, f"UID {cursor + 1}:*")
        if status != "OK":
            logger.warning("[IMAP] UID SEARCH failed: status=%s", status)
            return []

        raw_ids = messages[0].split() if messages and messages[0] else []
        uids: list[int] = []
        for raw in raw_ids:
            try:
                u = int(raw)
            except (TypeError, ValueError):
                continue
            # IMAP "UID N:*" siempre devuelve al menos un resultado (el UID
            # más alto), incluso si N supera UIDNEXT. Filtrar los <= cursor
            # protege contra ese caso borde.
            if u > cursor:
                uids.append(u)
        uids.sort()

        emails: list[dict] = []
        for uid in uids:
            try:
                # BODY.PEEK[] obtiene el contenido completo SIN marcar Seen.
                # El cliente decide cuándo (y si) marcar Seen vía mark_seen().
                res, data = self.mail.uid("FETCH", str(uid), "(BODY.PEEK[] UID)")
                if res != "OK" or not data:
                    logger.warning("[IMAP] UID FETCH %s failed: status=%s", uid, res)
                    continue
                raw_msg = None
                for response in data:
                    if isinstance(response, tuple) and len(response) >= 2:
                        raw_msg = response[1]
                        break
                if not raw_msg:
                    logger.warning("[IMAP] UID FETCH %s returned no payload", uid)
                    continue
                parsed = self.parse_email(email.message_from_bytes(raw_msg))
                parsed["uid"] = uid
                emails.append(parsed)
            except Exception as e:
                logger.error("[IMAP] Error fetching UID %s: %s", uid, e)
        return emails

    def mark_seen(self, uid: int) -> bool:
        """Marca el correo con el UID dado como \\Seen. Devuelve True si OK."""
        self._ensure_connected()
        try:
            status, _ = self.mail.uid("STORE", str(int(uid)), "+FLAGS", "(\\Seen)")
            ok = status == "OK"
            if not ok:
                logger.warning("[IMAP] UID STORE \\Seen %s failed: status=%s", uid, status)
            return ok
        except Exception as e:
            logger.error("[IMAP] Error marking UID %s as Seen: %s", uid, e)
            return False

    def parse_email(self, msg) -> dict:
        raw_subject = msg.get("Subject", "") or ""
        subject = ""
        try:
            decoded_parts = decode_header(raw_subject)
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    subject += part.decode(encoding or "utf-8", errors="replace")
                else:
                    subject += str(part)
        except Exception:
            subject = str(raw_subject)

        sender = msg.get("From", "unknown")
        message_id = msg.get("Message-ID", "unknown")
        in_reply_to = msg.get("In-Reply-To")
        references = msg.get("References")

        logger.debug("[IMAP] Parsing email ID=%s from=%s", message_id, sender)

        body = ""
        body_html = ""
        attachments = []
        inline_counter = 0

        if msg.is_multipart():
            for part in msg.walk():
                if part.is_multipart():
                    continue
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", "") or "").strip().lower()
                content_id = _normalize_content_id(part.get("Content-ID"))
                filename = _decode_mime_value(part.get_filename())
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue

                if content_type == "text/plain" and not filename and "attachment" not in content_disposition and not content_id:
                    try:
                        decoded_body = _decode_part_payload(part, payload)
                        if decoded_body and not body.strip():
                            body = decoded_body
                    except Exception as e:
                        logger.warning("[IMAP] Error decoding part %s: %s", content_type, e)
                    continue

                if content_type == "text/html" and not filename and "attachment" not in content_disposition:
                    try:
                        decoded_html = _decode_part_payload(part, payload)
                        if decoded_html and not body_html.strip():
                            body_html = decoded_html
                    except Exception as e:
                        logger.warning("[IMAP] Error decoding part %s: %s", content_type, e)
                    continue

                is_attachment_like = bool(filename or content_id or "attachment" in content_disposition or "inline" in content_disposition)
                if not is_attachment_like:
                    continue

                inline_counter += 1
                resolved_filename = filename or _fallback_inline_filename(content_type, content_id, inline_counter)
                attachments.append({
                    "filename": resolved_filename or "attachment.bin",
                    "content_type": content_type or "application/octet-stream",
                    "data_base64": base64.b64encode(payload).decode("ascii"),
                    "content_id": content_id,
                    "disposition": content_disposition,
                    "is_inline": bool(content_id or "inline" in content_disposition),
                })
        else:
            content_type = msg.get_content_type()
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    decoded = _decode_part_payload(msg, payload)
                    if content_type == "text/html":
                        body_html = decoded
                    else:
                        body = decoded
            except Exception as e:
                logger.warning("[IMAP] Error decoding single-part email: %s", e)

        if not body.strip() and body_html.strip():
            body = clean_html_content(body_html)

        return {
            "subject": subject,
            "sender": sender,
            "body": body,
            "body_html": body_html,
            "message_id": message_id,
            "in_reply_to": in_reply_to,
            "references": references,
            "attachments": attachments,
        }

    def close(self) -> None:
        if self.mail is None:
            return
        try:
            self.mail.close()
            self.mail.logout()
        except Exception:
            pass
        finally:
            self.mail = None
