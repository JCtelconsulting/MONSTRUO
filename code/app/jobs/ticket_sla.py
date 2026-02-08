"""
SLA (Service Level Agreement) checker for tickets (ESPAÑOL compatible).
Runs periodically to escalate overdue tickets.
"""
from datetime import datetime, timedelta
from app.core import db, notifications
import asyncio

async def check_ticket_sla(payload: dict = None):
    """
    Job handler: Revisa tickets vencidos y los escala.
    
    Logic:
    - Buscar tickets donde vence_at < NOW y estado != cerrado
    - Escalar severidad a 'critica'
    - Notificar
    """
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        
        # Encontrar tickets vencidos (versión español)
        cursor = conn.execute("""
            SELECT id, titulo, severidad, asignado_a, vence_at
            FROM tickets
            WHERE vence_at IS NOT NULL
              AND vence_at < ?
              AND estado NOT IN ('cerrado', 'resuelto')
              AND severidad != 'critica'
        """, (now,))
        
        overdue = cursor.fetchall()
        
        if not overdue:
            print(f"[SLA] No se encontraron tickets vencidos.")
        else:
            print(f"[SLA] Se encontraron {len(overdue)} tickets vencidos. Escalando...")
            
            for ticket in overdue:
                ticket_id = ticket["id"]
                titulo = ticket["titulo"]
                asignado = ticket["asignado_a"]
                vence = ticket["vence_at"]
                
                # Escalar a 'critica'
                conn.execute("""
                    UPDATE tickets 
                    SET severidad = 'critica', updated_at = ?
                    WHERE id = ?
                """, (now, ticket_id))
                
                print(f"[SLA] Ticket #{ticket_id} '{titulo}' escalado a critica (vencía: {vence})")
                
                # Notificación
                notifications.notify_ticket_escalation(ticket_id, titulo, asignado)
            
            conn.commit()
            print(f"[SLA] Escalamiento completado. {len(overdue)} tickets actualizados.")
        
    except Exception as e:
        print(f"[SLA] Error revisando SLA: {e}")
        raise
    finally:
        conn.close()
    
    # Re-encolar para próxima ejecución
    if payload and payload.get("recurring"):
        from app.core import jobs_engine
        now_iso = db.now_utc_iso()
        next_run = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
        
        # Re-encolar evitando duplicados
        conn2 = db.get_conn()
        try:
            exists = conn2.execute(
                "SELECT 1 FROM sys_jobs WHERE job_type='CHECK_TICKET_SLA' AND status IN ('PENDING','RETRY')"
            ).fetchone()
            if not exists:
                conn2.execute(
                    """INSERT INTO sys_jobs 
                       (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
                       VALUES ('CHECK_TICKET_SLA', 'PENDING', '{"recurring": true}', ?, 0, 1, ?, ?)""",
                    (next_run, now_iso, now_iso)
                )
                conn2.commit()
                print(f"[SLA] Próximo chequeo programado para {next_run}")
            else:
                print("[SLA] Job recurrente ya pendiente, no se re-encola.")
        finally:
            conn2.close()
