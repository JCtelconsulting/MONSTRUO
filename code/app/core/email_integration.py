import imaplib
import email
from email.header import decode_header
import re
import html
import base64
from app.core import db

def get_imap_config():
    conn = db.get_conn()
    try:
        keys = ['imap_host', 'imap_port', 'imap_user', 'imap_password', 'email_polling_interval']
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
                
        if not config.get('imap_host'): return None
        return config
    finally:
        conn.close()

def clean_html_content(html_content: str) -> str:
    """
    Cleans HTML content to plain text using regex.
    Removes scripts, styles, and extra whitespace.
    """
    if not html_content:
        return ""
        
    # Remove script and style elements
    clean = re.sub(r'<(script|style).*?>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '\n', clean)
    
    # Decode HTML entities
    clean = html.unescape(clean)
    
    # Collapse whitespace
    lines = [line.strip() for line in clean.splitlines()]
    clean = '\n'.join([line for line in lines if line])
    
    return clean

class EmailProcessor:
    def __init__(self):
        self.config = get_imap_config()

    def connect(self):
        if not self.config:
            raise ValueError("No IMAP config found")
            
        host = self.config['imap_host']
        port = int(self.config.get('imap_port', 993))
        user = self.config['imap_user']
        password = self.config['imap_password']
        
        self.mail = imaplib.IMAP4_SSL(host, port, timeout=30)
        self.mail.login(user, password)
        
    def fetch_unread(self):
        self.mail.select("inbox")
        status, messages = self.mail.search(None, 'UNSEEN')
        if status != "OK":
            return []
            
        email_ids = messages[0].split()
        emails = []
        
        for e_id in email_ids:
            try:
                res, msg = self.mail.fetch(e_id, "(RFC822)")
                for response in msg:
                    if isinstance(response, tuple):
                        msg = email.message_from_bytes(response[1])
                        parsed = self.parse_email(msg)
                        emails.append(parsed)
            except Exception as e:
                print(f"[IMAP] Error fetching email {e_id}: {e}")
                
        return emails
        
    def parse_email(self, msg):
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
        
        print(f"[IMAP] Parsing email ID={message_id} from={sender}")
        
        body = ""
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition.lower():
                    filename = part.get_filename()
                    if filename:
                        try:
                            decoded_header = decode_header(filename)[0]
                            filename_decoded, enc = decoded_header
                            if isinstance(filename_decoded, bytes):
                                filename_decoded = filename_decoded.decode(enc or "utf-8", errors="replace")
                        except Exception:
                            filename_decoded = str(filename)
                            
                        payload = part.get_payload(decode=True) or b""
                        attachments.append(
                            {
                                "filename": filename_decoded or "attachment.bin",
                                "content_type": content_type or "application/octet-stream",
                                "data_base64": base64.b64encode(payload).decode("ascii"),
                            }
                        )
                    continue

                if content_type in ["text/plain", "text/html"] and "attachment" not in content_disposition.lower():
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        payload = part.get_payload(decode=True)
                        if payload:
                            decoded_body = payload.decode(charset, errors="replace")
                            if content_type == "text/plain":
                                body = decoded_body
                            elif not body.strip():
                                body = clean_html_content(decoded_body)
                    except Exception as e:
                        print(f"[IMAP] Error decoding part {content_type}: {e}")
        else:
            content_type = msg.get_content_type()
            try:
                charset = msg.get_content_charset() or "utf-8"
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(charset, errors="replace")
                    if content_type == "text/html":
                        body = clean_html_content(body)
            except Exception as e:
                print(f"[IMAP] Error decoding single-part email: {e}")
                
        return {
            "subject": subject,
            "sender": sender,
            "body": body,
            "message_id": message_id,
            "in_reply_to": in_reply_to,
            "references": references,
            "attachments": attachments,
        }
        
    def close(self):
        try:
            self.mail.close()
            self.mail.logout()
        except:
            pass
