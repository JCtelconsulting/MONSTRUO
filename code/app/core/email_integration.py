import imaplib
import email
from email.header import decode_header
import re
import html
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
        
        self.mail = imaplib.IMAP4_SSL(host, port)
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
        subject, encoding = decode_header(raw_subject)[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8", errors="ignore")
            
        sender = msg.get("From")
        message_id = msg.get("Message-ID")
        in_reply_to = msg.get("In-Reply-To")
        references = msg.get("References")
        
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    body = part.get_payload(decode=True).decode()
                    break # Prefer plain text
                elif content_type == "text/html" and "attachment" not in content_disposition:
                    html_body = part.get_payload(decode=True).decode()
                    body = clean_html_content(html_body)
        else:
            content_type = msg.get_content_type()
            body = msg.get_payload(decode=True).decode()
            if content_type == "text/html":
                body = clean_html_content(body)
                
        return {
            "subject": subject,
            "sender": sender,
            "body": body,
            "message_id": message_id,
            "in_reply_to": in_reply_to,
            "references": references,
        }
        
    def close(self):
        try:
            self.mail.close()
            self.mail.logout()
        except:
            pass
