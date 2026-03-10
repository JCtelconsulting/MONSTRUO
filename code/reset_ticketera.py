import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from app.core import db

# Tablas estrictamente operacionales (tickets y su historial)
# Excluímos configuración como user_specialties, ticket_automation_rules, etc.
OPERATIONAL_TABLES = [
    "tks.ticket_email_draft_attachments",
    "tks.ticket_email_drafts",
    "tks.ticket_emails",
    "tks.ticket_notification_attempts",
    "tks.ticket_notifications",
    "tks.ticket_transitions",
    "tks.ticket_approvals",
    "tks.ticket_legal_holds",
    "tks.ticket_attachments",
    "tks.ticket_comments",
    "tks.tickets"
]

def reset_ticketera():
    print("Iniciando reinicio de datos de ticketera a cero...")
    conn = db.get_conn()
    try:
        for table in OPERATIONAL_TABLES:
            # CASCADE ensures that if there are any dependent rows, they are also deleted 
            # (though we are truncating almost all related tables anyway)
            print(f"Vaciando tabla: {table}")
            conn.execute(f"TRUNCATE TABLE {table} CASCADE;")
            
        conn.commit()
        print("✅ Ticketera reiniciada con éxito. Todos los tickets y su historial han sido eliminados.")
    except Exception as e:
        conn.rollback()
        print(f"❌ ERROR al reiniciar la ticketera: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    reset_ticketera()
