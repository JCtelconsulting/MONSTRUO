from datetime import datetime
from app.core import db

from pathlib import Path

# In a real system, this would integrate with SMTP or Slack API.
# For now, we simulate by writing to a dedicated log file.
# code/app/core/notifications.py -> parents[3] = root
LOG_FILE = Path(__file__).resolve().parents[3] / "notifications.log"

def send_notification(user_id: str, message: str, severity: str = "INFO"):
    """
    Send a notification to a local user.
    mvp: Write to notifications.log
    """
    timestamp = datetime.now().isoformat()
    
    # 1. Console Output (for debugging/docker logs)
    print(f"[NOTIF][{severity}] To {user_id}: {message}")
    
    # 2. Append to Log File (mvp inbox)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{timestamp}] [{severity}] User: {user_id} | Msg: {message}\n")
    except Exception as e:
        print(f"Failed to write notification log: {e}")

# Map job severities or others
def notify_ticket_escalation(ticket_id: int, title: str, assignee_id: str):
    msg = f"TICKET #{ticket_id} '{title}' has ESCALATED to CRITICAL due to SLA breach."
    # Notify assignee if exists, else notify admins/ops channel
    target = assignee_id if assignee_id else "OPS_CHANNEL"
    send_notification(target, msg, "CRITICAL")
