import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Optional
from app.core import db

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
    conf = get_smtp_config()
    if not conf:
        print("[EMAIL] No SMTP config found")
        return False
        
    host = conf.get('smtp_host')
    port = int(conf.get('smtp_port', 587))
    user = conf.get('smtp_user')
    password = conf.get('smtp_password')
    from_name = conf.get('smtp_from_name', 'Cobranza Monstruo')
    
    msg = MIMEMultipart()
    msg['From'] = f"{from_name} <{user}>"
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(html_body, 'html'))
    
    print(f"[EMAIL] Connecting to {host}:{port} as {user}...")
    
    try:
        s = smtplib.SMTP(host, port)
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
        s.quit()
        print(f"[EMAIL] Sent to {to_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
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
    conf = get_smtp_config()
    if not conf:
        print("[EMAIL] No SMTP config found")
        return False

    to_emails = [e.strip() for e in (to_emails or []) if e and e.strip()]
    cc_emails = [e.strip() for e in (cc_emails or []) if e and e.strip()]
    if not to_emails:
        raise ValueError("to_emails vacío")

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
            print(f"[EMAIL] Attachment error ({a.get('filename')}): {e}")

    recipients = to_emails + cc_emails
    print(f"[EMAIL] Connecting to {host}:{port} as {user}... ({len(recipients)} recipients)")

    try:
        s = smtplib.SMTP(host, port)
        s.starttls()
        s.login(user, password)
        s.sendmail(msg["From"], recipients, msg.as_string())
        s.quit()
        print(f"[EMAIL] Sent to {', '.join(to_emails)}")
        return True
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
        raise e
