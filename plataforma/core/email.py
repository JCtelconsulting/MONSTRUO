import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import make_msgid
from typing import Optional
from plataforma.core import db
from plataforma.core.config import settings
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def get_smtp_config():
    conn = db.get_conn()
    try:
        keys = ['smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'smtp_from_name']
        placeholders = ', '.join(['%s' for _ in keys])
        query = f"SELECT key, value FROM system_settings WHERE key IN ({placeholders})"
        cursor = conn.execute(query, tuple(keys))
        rows = cursor.fetchall()
        
        config = {}
        for r in rows:
            if isinstance(r, dict):
                config[r['key']] = r['value']
            else:
                config[r[0]] = r[1]
                
        # Validate existence
        if not config.get('smtp_host'): return None
        return config
    finally:
        conn.close()

def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Sends an email using stored SMTP credentials.
    Returns True on success, raises Exception on failure.
    """
    try:
        send_email_advanced(to_email, subject, html_body)
        return True
    except RuntimeError:
        # Retro-compatibilidad: algunos flujos esperan False si no hay SMTP configurado.
        return False


def send_email_advanced(
    to_email: str,
    subject: str,
    html_body: str,
    headers: Optional[dict[str, str]] = None,
    attachments: Optional[list[dict]] = None,
    cc_emails: Optional[list[str]] = None,
    bcc_emails: Optional[list[str]] = None,
) -> dict:
    """
    Sends a single email and supports custom headers (e.g. In-Reply-To, References).
    Returns metadata including generated Message-ID for threading.
    """
    conf = get_smtp_config()
    if not conf:
        raise RuntimeError("SMTP no configurado")

    host = conf.get("smtp_host")
    port = int(conf.get("smtp_port", 587))
    user = conf.get("smtp_user")
    password = conf.get("smtp_password")
    from_name = conf.get("smtp_from_name", "Cobranza Monstruo")

    # MAIL_SANDBOX es kill-switch absoluto: bloquea siempre, sin importar
    # EMAIL_FORCE_ENABLE u otros overrides. Pensado para impedir incidentes
    # como el del 2026-05-13 donde DEV envió auto-replies reales.
    if settings.MAIL_SANDBOX or (settings.ENV_TYPE != "prod" and not os.getenv("EMAIL_FORCE_ENABLE")):
        logger.info(f"[EMAIL_MOCK] Would send to {to_email} subject '{subject}' (ENV={settings.ENV_TYPE}, SANDBOX={settings.MAIL_SANDBOX})")
        if attachments:
            logger.info(f"[EMAIL_MOCK] Attachments: {[a['filename'] for a in attachments]}")
        return {
            "to_email": str(to_email or "").strip(),
            "cc_emails": [str(x).strip() for x in (cc_emails or []) if str(x or "").strip()],
            "bcc_emails": [str(x).strip() for x in (bcc_emails or []) if str(x or "").strip()],
            "from_addr": user,
            "message_id": f"mock-{int(datetime.utcnow().timestamp())}@monstruo.dev"
        }

    msg = MIMEMultipart()
    msg["From"] = f"{from_name} <{user}>"
    to_addr = str(to_email or "").strip()
    if not to_addr:
        raise ValueError("to_email vacío")
    cc_list = []
    cc_seen = set()
    for raw in (cc_emails or []):
        email = str(raw or "").strip()
        if not email:
            continue
        if email.lower() == to_addr.lower():
            continue
        lowered = email.lower()
        if lowered in cc_seen:
            continue
        cc_seen.add(lowered)
        cc_list.append(email)

    bcc_list = []
    bcc_seen = set()
    for raw in (bcc_emails or []):
        email = str(raw or "").strip()
        if not email:
            continue
        lowered = email.lower()
        if lowered == to_addr.lower():
            continue
        if lowered in cc_seen:
            continue
        if lowered in bcc_seen:
            continue
        bcc_seen.add(lowered)
        bcc_list.append(email)

    msg["To"] = to_addr
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject

    generated_msg_id = make_msgid()
    msg["Message-ID"] = generated_msg_id

    for header_name, header_value in (headers or {}).items():
        if header_name and header_value:
            msg[header_name] = str(header_value)

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Manejar adjuntos si existen (unificación con lógica de send_email_with_attachments)
    if attachments:
        for a in attachments:
            try:
                filename = a.get("filename") or "archivo"
                data = a.get("data") or b""
                part = MIMEApplication(data)
                part.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(part)
            except Exception as e:
                logger.warning("[EMAIL] Attachment error (%s): %s", a.get("filename"), e)

    # Blindaje DEV/PROD: MAIL_SANDBOX como kill-switch absoluto.
    if settings.MAIL_SANDBOX or (settings.ENV_TYPE != "prod" and not os.getenv("EMAIL_FORCE_ENABLE")):
        logger.info("[EMAIL_MOCK] Would send to %s subject '%s' (ENV=%s, SANDBOX=%s)", to_addr, subject, settings.ENV_TYPE, settings.MAIL_SANDBOX)
        return {
            "ok": True,
            "to_email": to_addr,
            "cc_emails": cc_list,
            "bcc_emails": bcc_list,
            "from_addr": user,
            "message_id": generated_msg_id,
            "mock": True
        }

    logger.info("[EMAIL] Connecting to %s:%s as %s...", host, port, user)
    try:
        s = smtplib.SMTP(host, port)
        s.starttls()
        s.login(user, password)
        recipients = [to_addr] + cc_list + bcc_list
        s.sendmail(msg["From"], recipients, msg.as_string())
        s.quit()
        logger.info("[EMAIL] Sent to %s", to_addr)
        return {
            "ok": True,
            "to_email": to_addr,
            "cc_emails": cc_list,
            "bcc_emails": bcc_list,
            "from_addr": user,
            "message_id": generated_msg_id,
        }
    except Exception as e:
        logger.error("[EMAIL] Error: %s", e)
        raise e


def send_email_with_attachments(
    to_emails: list[str],
    subject: str,
    html_body: str,
    cc_emails: Optional[list[str]] = None,
    attachments: Optional[list[dict]] = None,
) -> bool:
    """
    Sends an email with optional attachments.
    attachments: [{"filename": "x.pdf", "content_type": "application/pdf", "data": b"..."}]
    """
    to_emails = [e.strip() for e in (to_emails or []) if e and e.strip()]
    cc_emails = [e.strip() for e in (cc_emails or []) if e and e.strip()]
    if not to_emails:
        raise ValueError("to_emails vacío")

    if settings.MAIL_SANDBOX or (settings.ENV_TYPE != "prod" and not os.getenv("EMAIL_FORCE_ENABLE")):
        logger.info(f"[EMAIL_MOCK] Would send to {to_emails} subject '{subject}' (ENV={settings.ENV_TYPE}, SANDBOX={settings.MAIL_SANDBOX})")
        return True

    conf = get_smtp_config()
    if not conf:
        logger.warning("[EMAIL] No SMTP config found")
        return False

    host = conf.get("smtp_host")
    port = int(conf.get("smtp_port", 587))
    user = conf.get("smtp_user")
    password = conf.get("smtp_password")
    from_name = conf.get("smtp_from_name", "Cobranza Monstruo")

    msg = MIMEMultipart()
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = ", ".join(to_emails)
    if cc_emails:
        msg["Cc"] = ", ".join(cc_emails)
    msg["Subject"] = subject

    msg.attach(MIMEText(html_body, "html"))

    for a in attachments or []:
        try:
            filename = a.get("filename") or "archivo"
            data = a.get("data") or b""
            part = MIMEApplication(data)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
        except Exception as e:
            logger.warning("[EMAIL] Attachment error (%s): %s", a.get("filename"), e)

    recipients = to_emails + cc_emails
    logger.info("[EMAIL] Connecting to %s:%s as %s... (%s recipients)", host, port, user, len(recipients))

    try:
        s = smtplib.SMTP(host, port)
        s.starttls()
        s.login(user, password)
        s.sendmail(msg["From"], recipients, msg.as_string())
        s.quit()
        logger.info("[EMAIL] Sent to %s", ", ".join(to_emails))
        return True
    except Exception as e:
        logger.error("[EMAIL] Error: %s", e)
        raise e
