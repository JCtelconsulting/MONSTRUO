"""
SLA (Service Level Agreement) checker for tickets (ESPAÑOL compatible).
Runs periodically to escalate overdue tickets.
"""
from datetime import datetime, timedelta, timezone

from app.core import db, notifications, jobs_engine, tickets_service


def _next_run_iso(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=max(1, int(minutes or 1)))).isoformat()


async def _schedule_unique(job_type: str, payload: dict, minutes: int, max_retries: int) -> None:
    await jobs_engine.enqueue_unique_job(
        job_type,
        payload,
        max_retries=max_retries,
        next_run_at=_next_run_iso(minutes),
        update_existing_next_run=False,
    )

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
        await _schedule_unique("CHECK_TICKET_SLA", {"recurring": True}, minutes=30, max_retries=1)


async def evaluate_ticket_sla_job(payload: dict = None):
    payload = payload or {}
    limit = max(1, min(int(payload.get("limit", 500) or 500), 5000))
    result = tickets_service.run_sla_evaluation_batch(limit=limit)
    print(
        f"[SLA_EVAL] Processed={result.get('processed', 0)} "
        f"limit={limit} at={result.get('evaluated_at')}"
    )
    if payload.get("recurring", True):
        await _schedule_unique(
            "TKS_SLA_EVALUATE",
            {"recurring": True, "limit": limit},
            minutes=5,
            max_retries=1,
        )
