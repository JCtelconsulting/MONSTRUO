from app.core import db
import json

def log_audit(actor: str, action: str, target: str = "", ip: str = "", severity: str = "info", metadata: dict = None):
    try:
        conn = db.get_conn()
        meta_str = json.dumps(metadata) if metadata else ""
        conn.execute(
            "INSERT INTO audit_logs (timestamp, actor, action, target, ip_address, severity, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (db.now_utc_iso(), actor, action, target, ip, severity, meta_str)
        )
        conn.commit()
    except Exception as e:
        print(f"AUDIT FAIL: {e}")
    finally:
        conn.close()
