from typing import List, Optional, Dict, Any
from app.core import db
from datetime import datetime, timedelta

def create_ticket(
    titulo: str, 
    descripcion: str, 
    creador_id: str, 
    severidad: str = "media",
    tipo: str = "incidencia"
) -> Dict[str, Any]:
    """Crear un nuevo ticket."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        # Calcular vencimiento sugerido (SLA simple)
        vence_at = None
        sla_hours = {"baja": 168, "media": 72, "alta": 24, "critica": 4}
        hours = sla_hours.get(severidad.lower(), 72)
        vence_at = (datetime.fromisoformat(now) + timedelta(hours=hours)).isoformat()

        cursor = conn.execute(
            """INSERT INTO tickets 
               (titulo, descripcion, estado, severidad, tipo, creador_id, vence_at, created_at, updated_at) 
               VALUES (?, ?, 'abierto', ?, ?, ?, ?, ?, ?) RETURNING id""",
            (titulo, descripcion, severidad, tipo, creador_id, vence_at, now, now)
        )
        row = cursor.fetchone()
        ticket_id = row["id"] if row else None
        
        # Registrar evento inicial
        add_comment(ticket_id, "system", "Ticket creado automáticamente", "creacion")
        
        conn.commit()
        return get_ticket(ticket_id)
    finally:
        conn.close()

def get_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    """Obtener un ticket por ID."""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_tickets(
    estado: Optional[str] = None, 
    q: Optional[str] = None, 
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Listar tickets con filtros."""
    conn = db.get_conn()
    try:
        sql = "SELECT * FROM tickets WHERE 1=1"
        params = []
        
        if estado:
            sql += " AND estado = ?"
            params.append(estado.lower())
        
        if q:
            sql += " AND (titulo LIKE ? OR descripcion LIKE ?)"
            params.append(f"%{q}%")
            params.append(f"%{q}%")
            
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def update_ticket(ticket_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Actualizar campos del ticket."""
    allowed_keys = {"estado", "severidad", "asignado_a", "titulo", "descripcion", "vence_at"}
    keys_to_update = [k for k in updates.keys() if k in allowed_keys]
    
    if not keys_to_update:
        return get_ticket(ticket_id)
        
    conn = db.get_conn()
    try:
        set_clause = ", ".join([f"{k} = ?" for k in keys_to_update])
        set_clause += ", updated_at = ?"
        
        params = [updates[k] for k in keys_to_update]
        params.append(db.now_utc_iso())
        params.append(ticket_id)
        
        cursor = conn.execute(f"UPDATE tickets SET {set_clause} WHERE id = ?", params)
        if cursor.rowcount == 0:
            return None
        
        # Registrar evento de cambio si aplica
        if "estado" in updates:
            add_comment(ticket_id, "system", f"Estado cambiado a {updates['estado']}", "cambio_estado")
            
        conn.commit()
        return get_ticket(ticket_id)
    finally:
        conn.close()

def add_comment(ticket_id: int, user_id: str, content: str, event_type: str = "comentario") -> Dict[str, Any]:
    """Agregar un comentario/evento al ticket."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        cursor = conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at) 
               VALUES (?, ?, ?, ?) RETURNING id""",
            (ticket_id, user_id, f"[{event_type.upper()}] {content}", now)
        )
        row = cursor.fetchone()
        comment_id = row["id"] if row else None
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        conn.commit()
        
        row = conn.execute("SELECT * FROM ticket_comments WHERE id = ?", (comment_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()

def get_timeline(ticket_id: int) -> List[Dict[str, Any]]:
    """Línea de tiempo unificada para la UI."""
    conn = db.get_conn()
    try:
        # Usamos los comentarios como eventos.
        cursor = conn.execute(
            "SELECT * FROM ticket_comments WHERE ticket_id = ? ORDER BY created_at DESC", 
            (ticket_id,)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            content = r["content"]
            # Extraer tipo si viene en el formato [TIPO]
            event_name = "Nota"
            detail = content
            if content.startswith("["):
                parts = content.split("]", 1)
                event_name = parts[0][1:].capitalize()
                detail = parts[1].strip()
                
            result.append({
                "creado_at": r["created_at"],
                "evento": event_name,
                "detalle": detail,
                "usuario": r["user_id"]
            })
        return result
    finally:
        conn.close()

def get_stats() -> Dict[str, Any]:
    """Obtener métricas para Dashboard."""
    conn = db.get_conn()
    try:
        stats = {
            "by_status": {},
            "by_prio": {},
            "pivot_assignee": {}
        }
        
        # 1. Por Estado
        rows = conn.execute("SELECT estado, COUNT(*) as c FROM tickets GROUP BY estado").fetchall()
        for r in rows:
            stats["by_status"][r["estado"]] = r["c"]
            
        # 2. Por Severidad
        rows = conn.execute("SELECT severidad, COUNT(*) as c FROM tickets GROUP BY severidad").fetchall()
        for r in rows:
            stats["by_prio"][r["severidad"]] = r["c"]
            
        # 3. Pivot: Assignee vs Status
        rows = conn.execute("SELECT asignado_a, estado, COUNT(*) as c FROM tickets GROUP BY asignado_a, estado").fetchall()
        for r in rows:
            assignee = r["asignado_a"] or "Sin Asignar"
            status = r["estado"]
            count = r["c"]
            
            if assignee not in stats["pivot_assignee"]:
                stats["pivot_assignee"][assignee] = {"total": 0}
                
            stats["pivot_assignee"][assignee][status] = count
            stats["pivot_assignee"][assignee]["total"] += count
            
        return stats
    finally:
        conn.close()
