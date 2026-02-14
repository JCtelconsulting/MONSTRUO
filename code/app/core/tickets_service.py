"""
Ticketera V3 — Servicio profesional de Mesa de Ayuda.
Auto-clasificación, auto-asignación, notificaciones escalonadas, SLA.
"""
from typing import List, Optional, Dict, Any
from app.core import db
from datetime import datetime, timedelta
import json
import html
import logging
import re
import asyncio
from email.utils import parseaddr
from app.core import email_integration, email as email_sender, jobs_engine
from app.core.config import settings as app_settings

logger = logging.getLogger(__name__)

# ==========================================================================
# CONSTANTES
# ==========================================================================
CATEGORIAS_VALIDAS = {"redes", "sistemas", "ejecucion", "admin", "general"}
ESTADOS_VALIDOS = {"abierto", "en_progreso", "resuelto", "cerrado"}
SEVERIDADES_VALIDAS = {"baja", "media", "alta", "critica"}
ROLES_TECNICOS = ("redes", "sistemas", "implementaciones", "ops")

SLA_HORAS = {
    "baja": 168,    # 7 días
    "media": 72,    # 3 días
    "alta": 24,     # 1 día
    "critica": 4,   # 4 horas
}

PRIORIDAD_MAP = {
    "critica": 1,
    "alta": 2,
    "media": 3,
    "baja": 4,
}

# Keywords para auto-clasificación (se buscan en título + descripción)
KEYWORDS_CATEGORIAS = {
    "redes": [
        "red", "network", "switch", "router", "firewall", "vpn", "wifi",
        "internet", "dns", "dhcp", "ip", "conectividad", "fibra",
        "ping", "latencia", "cable", "lan", "wan", "vlan", "mikrotik",
        "ubiquiti", "cisco", "fortigate", "enlace",
    ],
    "sistemas": [
        "servidor", "server", "windows", "linux", "backup", "base de datos",
        "correo", "email", "office", "365", "azure", "nube", "cloud",
        "software", "licencia", "antivirus", "actualización", "update",
        "disco", "almacenamiento", "virtualización", "vmware", "hyper-v",
    ],
    "ejecucion": [
        "instalación", "montaje", "cableado", "obra", "terreno",
        "rack", "ups", "eléctric", "canalización", "patch panel",
        "certificación", "fusión", "fibra óptica", "poste",
        "cámara", "cctv", "control de acceso",
    ],
    "admin": [
        "factura", "boleta", "pago", "cobro", "cotización", "presupuesto",
        "contrato", "renovación", "licencia", "usuario", "contraseña",
        "acceso", "permiso", "cuenta",
    ],
}


# ==========================================================================
# CLASIFICACIÓN AUTOMÁTICA
# ==========================================================================
def clasificar_ticket(titulo: str, descripcion: str) -> str:
    """Clasifica un ticket basado en keywords en título y descripción."""
    texto = f"{titulo} {descripcion}".lower()
    scores = {}
    for cat, keywords in KEYWORDS_CATEGORIAS.items():
        score = sum(1 for kw in keywords if kw in texto)
        if score > 0:
            scores[cat] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)


# ==========================================================================
# AUTO-ASIGNACIÓN
# ==========================================================================
def auto_asignar(categoria: str) -> Optional[str]:
    """
    Asigna al técnico con menor carga en la categoría.
    Round-robin por menor current_load.
    """
    conn = db.get_conn()
    try:
        role_placeholders = ", ".join(["?"] * len(ROLES_TECNICOS))
        row = conn.execute(
            f"""
            SELECT us.username
            FROM user_specialties us
            JOIN users u ON u.username = us.username
            WHERE us.specialty = ?
              AND us.is_available = 1
              AND us.current_load < us.max_load
              AND COALESCE(u.is_active, 1) = 1
              AND u.role IN ({role_placeholders})
            ORDER BY us.current_load ASC, us.updated_at ASC NULLS FIRST, us.username ASC
            LIMIT 1
            """,
            (categoria, *ROLES_TECNICOS),
        ).fetchone()

        if row:
            username = row["username"]
            # Incrementar carga
            conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (db.now_utc_iso(), username, categoria))
            conn.commit()
            return username

        logger.debug(f"auto_asignar failed for '{categoria}', trying fallback")

        # Fallback: si no hay técnico exacto en esa categoría, asignar al técnico
        # disponible con menor carga (solo roles técnicos activos).
        row = conn.execute(
            f"""
            SELECT us.username, us.specialty
            FROM user_specialties us
            JOIN users u ON u.username = us.username
            WHERE us.is_available = 1
              AND us.current_load < us.max_load
              AND COALESCE(u.is_active, 1) = 1
              AND u.role IN ({role_placeholders})
            ORDER BY us.current_load ASC, us.updated_at ASC NULLS FIRST, us.username ASC
            LIMIT 1
            """,
            ROLES_TECNICOS,
        ).fetchone()

        if row:
            username = row["username"]
            specialty = row["specialty"]
            conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (db.now_utc_iso(), username, specialty))
            conn.commit()
            return username

        return None
    finally:
        conn.close()


def incrementar_carga(username: str, specialty: Optional[str] = None) -> None:
    """Incrementa la carga del técnico al asignar un ticket. Si se especifica especialidad, solo incrementa esa."""
    if not username:
        return
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        # Intentar incrementar en la especialidad específica
        if specialty:
            cursor = conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, specialty))
            
            if cursor.rowcount > 0:
                conn.commit()
                return

        # Fallback 1: si existe una especialidad 'general', usarla.
        cursor = conn.execute("""
            UPDATE user_specialties
            SET current_load = current_load + 1, updated_at = ?
            WHERE username = ? AND specialty = 'general'
        """, (now, username))

        if cursor.rowcount > 0:
            conn.commit()
            return

        # Fallback 2: elegir la especialidad más liviana del usuario.
        row = conn.execute("""
            SELECT specialty
            FROM user_specialties
            WHERE username = ?
            ORDER BY current_load ASC, updated_at ASC NULLS FIRST, specialty ASC
            LIMIT 1
        """, (username,)).fetchone()
        if row:
            conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, row["specialty"]))
        conn.commit()
    finally:
        conn.close()


def decrementar_carga(username: str, specialty: Optional[str] = None) -> None:
    """Decrementa la carga del técnico. Si se especifica especialidad, intenta decretar esa."""
    if not username:
        return
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        # Intentar decrementar en la especialidad específica
        if specialty:
            cursor = conn.execute("""
                UPDATE user_specialties
                SET current_load = GREATEST(current_load - 1, 0), updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, specialty))
            
            if cursor.rowcount > 0:
                conn.commit()
                return

        # Fallback 1: decrementar en 'general' si existe.
        cursor = conn.execute("""
            UPDATE user_specialties
            SET current_load = GREATEST(current_load - 1, 0), updated_at = ?
            WHERE username = ? AND specialty = 'general'
        """, (now, username))

        if cursor.rowcount > 0:
            conn.commit()
            return

        # Fallback 2: decrementar la especialidad con mayor carga.
        row = conn.execute("""
            SELECT specialty
            FROM user_specialties
            WHERE username = ?
            ORDER BY current_load DESC, updated_at ASC NULLS FIRST, specialty ASC
            LIMIT 1
        """, (username,)).fetchone()
        if row:
            conn.execute("""
                UPDATE user_specialties
                SET current_load = GREATEST(current_load - 1, 0), updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, row["specialty"]))
        conn.commit()
    finally:
        conn.close()


# ==========================================================================
# NOTIFICACIONES ESCALONADAS
# ==========================================================================
def programar_notificaciones(ticket_id: int, user_id: str) -> None:
    """
    Programa 3 niveles de notificación:
    1. Inmediato → in-app
    2. +5 min → WhatsApp/Telegram
    3. +20 min → Llamada 3CX
    """
    conn = db.get_conn()
    try:
        now = datetime.fromisoformat(db.now_utc_iso().replace("Z", "+00:00"))
        now_iso = now.isoformat()

        niveles = [
            (1, "app", now),
            (2, "whatsapp", now + timedelta(minutes=5)),
            (3, "3cx", now + timedelta(minutes=20)),
        ]

        for level, channel, scheduled in niveles:
            conn.execute("""
                INSERT INTO ticket_notifications
                (ticket_id, user_id, channel, status, escalation_level, scheduled_at, created_at)
                VALUES (?, ?, ?, 'pending', ?, ?, ?)
            """, (ticket_id, user_id, channel, level, scheduled.isoformat(), now_iso))

        conn.commit()
    finally:
        conn.close()


def marcar_notificacion_vista(ticket_id: int, user_id: str) -> None:
    """Cuando el técnico ve el ticket, cancela las notificaciones pendientes."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute("""
            UPDATE ticket_notifications
            SET status = 'cancelled', seen_at = ?
            WHERE ticket_id = ? AND user_id = ? AND status = 'pending'
        """, (now, ticket_id, user_id))
        conn.commit()
    finally:
        conn.close()


def get_notificaciones_pendientes(user_id: str) -> List[Dict[str, Any]]:
    """Obtiene notificaciones in-app pendientes para un usuario."""
    conn = db.get_conn()
    try:
        rows = conn.execute("""
            SELECT tn.*, t.titulo, t.codigo, t.severidad, t.categoria
            FROM ticket_notifications tn
            JOIN tickets t ON t.id = tn.ticket_id
            WHERE tn.user_id = ? AND tn.channel = 'app'
              AND tn.status IN ('pending', 'sent')
            ORDER BY tn.created_at DESC
            LIMIT 50
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


async def process_pending_notifications(payload: Dict[str, Any] = None):
    """
    Busca notificaciones pendientes (scheduled_at <= now, status=pending)
    y encola los jobs correspondientes (WHATSAPP_NOTIFY, 3CX_CALL).
    Si payload['recurring'] is True, se re-agenda a si mismo.
    """
    payload = payload or {}
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        # Seleccionar pendientes vencidos
        rows = conn.execute("""
            SELECT tn.id, tn.channel, tn.user_id, u.phone_number, t.codigo, t.titulo
            FROM ticket_notifications tn
            JOIN tickets t ON t.id = tn.ticket_id
            JOIN users u ON u.username = tn.user_id
            WHERE tn.status = 'pending' 
              AND tn.channel IN ('whatsapp', '3cx')
              AND tn.scheduled_at <= ?
            LIMIT 50
        """, (now,)).fetchall()

        if rows:
            from app.core import jobs_engine
            
            for r in rows:
                notif_id = r["id"]
                channel = r["channel"]
                phone = r["phone_number"]
                
                if not phone:
                    logger.warning(f"User {r['user_id']} has no phone for {channel} notification")
                    conn.execute("UPDATE ticket_notifications SET status='failed', seen_at=? WHERE id=?", (now, notif_id))
                    continue

                try:
                    if channel == "whatsapp":
                        msg = f"Ticket {r['codigo']}: {r['titulo']} requiere tu atención."
                        asyncio.create_task(jobs_engine.enqueue_job(
                            "WHATSAPP_NOTIFY", 
                            {"phone": phone, "message": msg, "notification_id": notif_id}
                        ))
                    elif channel == "3cx":
                        asyncio.create_task(jobs_engine.enqueue_job(
                            "3CX_CALL", 
                            {"phone": phone, "notification_id": notif_id}
                        ))
                    
                    conn.execute("UPDATE ticket_notifications SET status='sent', seen_at=? WHERE id=?", (now, notif_id))
                    
                except Exception as e:
                    logger.error(f"Error enququeing notification {notif_id}: {e}")
            conn.commit()
                    


        # Reschedule if recurring
        if payload.get("recurring"):
            from app.core import jobs_engine
            # Re-enqueue process
            await jobs_engine.enqueue_job("PROCESS_NOTIFICATIONS", {"recurring": True}, max_retries=0)
            
            # Delay next run by 60 seconds
            delay_seconds = 60
            next_run = (db.datetime.utcnow() + db.timedelta(seconds=delay_seconds)).isoformat()
            
            # Update the job we just inserted (highest ID for this type) to set correct next_run_at
            # Note: This relies on no other concurrent inserts stealing the 'MAX(id)'. 
            # In single worker scenarios this is fine.
            conn.execute(
                "UPDATE sys_jobs SET next_run_at = ? WHERE id = (SELECT MAX(id) FROM sys_jobs WHERE job_type='PROCESS_NOTIFICATIONS')", 
                (next_run,)
            )
            conn.commit()

    finally:
        conn.close()

    # Re-schedule logic is now inside try block to ensure it happens if no critical DB error prevents commit.
    # If critical error happens, we might lose the chain, which is acceptable for now vs infinite error loop.


# ==========================================================================
# GENERADOR DE CÓDIGO DE TICKET
# ==========================================================================
def generar_codigo(ticket_id: int) -> str:
    """Genera código TK-DD-MM-YYYY-NNNN."""
    now = datetime.now()
    return f"TK-{now.strftime('%d-%m-%Y')}-{ticket_id:04d}"


# ==========================================================================
# CRUD PRINCIPAL
# ==========================================================================
def create_ticket(
    titulo: str,
    descripcion: str,
    creador_id: str,
    severidad: str = "media",
    tipo: str = "incidencia",
    categoria: Optional[str] = None,
    origen_email: Optional[str] = None,
    cliente_nombre: Optional[str] = None,
    email_thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Crear un nuevo ticket con auto-clasificación y auto-asignación."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()

        # Normalizar severidad
        severidad = severidad.lower() if severidad else "media"
        if severidad not in SEVERIDADES_VALIDAS:
            severidad = "media"

        # Auto-clasificar si no se especifica categoría
        if not categoria or categoria not in CATEGORIAS_VALIDAS:
            categoria = clasificar_ticket(titulo, descripcion)

        # Calcular SLA
        sla_horas = SLA_HORAS.get(severidad, 72)
        vence_at = (datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(hours=sla_horas)).isoformat()

        # Prioridad numérica
        prioridad = PRIORIDAD_MAP.get(severidad, 3)

        # Auto-asignar (no-crítico: si falla, ticket se crea sin asignar)
        asignado_a = None
        try:
            asignado_a = auto_asignar(categoria)
        except Exception as e:
            logger.warning(f"[create_ticket] auto_asignar falló para categoría '{categoria}': {e}")

        cursor = conn.execute(
            """INSERT INTO tickets
               (titulo, descripcion, estado, severidad, tipo, creador_id,
                asignado_a, vence_at, created_at, updated_at,
                categoria, origen_email, cliente_nombre, prioridad, sla_horas, email_thread_id)
               VALUES (?, ?, 'abierto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (titulo, descripcion, severidad, tipo, creador_id,
             asignado_a, vence_at, now, now,
             categoria, origen_email, cliente_nombre, prioridad, sla_horas, email_thread_id)
        )
        row = cursor.fetchone()
        ticket_id = row["id"] if row else None

        # Validar que el INSERT retornó un ID válido
        if ticket_id is None:
            raise ValueError("INSERT INTO tickets no retornó un ID. Posible error en la base de datos.")

        # Generar código y actualizar
        codigo = generar_codigo(ticket_id)
        conn.execute("UPDATE tickets SET codigo = ? WHERE id = ?", (codigo, ticket_id))

        # Evento de creación
        conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, 'system', ?, ?)""",
            (ticket_id, f"[CREACION] Ticket creado. Categoría: {categoria}. Severidad: {severidad}.", now)
        )

        if asignado_a:
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, 'system', ?, ?)""",
                (ticket_id, f"[ASIGNACION] Auto-asignado a {asignado_a} (especialidad: {categoria})", now)
            )

        conn.commit()

        # Programar notificaciones escalonadas (no-crítico: si falla, ticket ya está creado)
        if asignado_a:
            try:
                programar_notificaciones(ticket_id, asignado_a)
            except Exception as e:
                logger.warning(f"[create_ticket] programar_notificaciones falló para ticket {ticket_id}: {e}")

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
    categoria: Optional[str] = None,
    asignado_a: Optional[str] = None,
    severidad: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    include_full: bool = False,
    include_total: bool = True,
) -> Dict[str, Any]:
    """Listar tickets con filtros avanzados. Retorna {items, total}."""
    conn = db.get_conn()
    try:
        # Protección simple para evitar cargas excesivas en UI.
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))

        where_clauses = ["1=1"]
        params = []

        if estado:
            where_clauses.append("estado = ?")
            params.append(estado.lower())

        if categoria:
            where_clauses.append("categoria = ?")
            params.append(categoria.lower())

        if asignado_a:
            where_clauses.append("asignado_a = ?")
            params.append(asignado_a)

        if severidad:
            where_clauses.append("severidad = ?")
            params.append(severidad.lower())

        if q:
            where_clauses.append("(titulo ILIKE ? OR descripcion ILIKE ? OR codigo ILIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

        where_sql = " AND ".join(where_clauses)

        total = 0
        if include_total:
            count_row = conn.execute(f"SELECT COUNT(*) as total FROM tickets WHERE {where_sql}", params).fetchone()
            total = count_row["total"] if count_row else 0

        # Para listados y kanban no necesitamos payload completo (descripcion puede ser muy grande).
        select_fields = (
            "*"
            if include_full
            else """
                id, codigo, titulo, estado, tipo, severidad, creador_id, asignado_a,
                vence_at, created_at, updated_at, categoria, origen_email, cliente_nombre,
                prioridad, email_thread_id, resolucion, sla_horas_bak, sla_horas
            """
        )

        # Obtener items
        items_params = params + [limit, offset]
        cursor = conn.execute(
            f"SELECT {select_fields} FROM tickets WHERE {where_sql} ORDER BY prioridad ASC, created_at DESC LIMIT ? OFFSET ?",
            items_params
        )
        items = [dict(row) for row in cursor.fetchall()]

        return {"items": items, "total": total if include_total else len(items)}
    finally:
        conn.close()


def update_ticket(ticket_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Actualizar campos del ticket."""
    allowed_keys = {
        "estado", "severidad", "asignado_a", "titulo", "descripcion",
        "vence_at", "categoria", "prioridad", "resolucion",
    }
    keys_to_update = [k for k in updates.keys() if k in allowed_keys]

    if not keys_to_update:
        return get_ticket(ticket_id)

    # Obtener ticket actual para lógica de carga
    current = get_ticket(ticket_id)
    if not current:
        return None

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        set_clause = ", ".join([f"{k} = ?" for k in keys_to_update])
        set_clause += ", updated_at = ?"

        params = [updates[k] for k in keys_to_update]
        params.append(now)
        params.append(ticket_id)

        cursor = conn.execute(f"UPDATE tickets SET {set_clause} WHERE id = ?", params)
        if cursor.rowcount == 0:
            return None

        # Registrar eventos
        if "estado" in updates:
            new_estado = updates["estado"]
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, 'system', ?, ?)""",
                (ticket_id, f"[CAMBIO_ESTADO] Estado cambiado a {new_estado}", now)
            )
            # Decrementar carga al cerrar/resolver
            if new_estado in ("cerrado", "resuelto") and current.get("asignado_a"):
                decrementar_carga(current["asignado_a"], specialty=current.get("categoria"))

        if "asignado_a" in updates:
            new_asignado = updates["asignado_a"]
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, 'system', ?, ?)""",
                (ticket_id, f"[REASIGNACION] Reasignado a {new_asignado}", now)
            )
            # Actualizar carga: decrementar viejo, incrementar nuevo
            # Usar 'categoria' del ticket (actual o nueva si se está actualizando)
            old_cat = current.get("categoria")
            new_cat = updates.get("categoria", old_cat)

            if current.get("asignado_a"):
                decrementar_carga(current["asignado_a"], specialty=old_cat)
            
            if new_asignado:
                incrementar_carga(new_asignado, specialty=new_cat)
                # Programar notificaciones para el nuevo asignado (fail-safe)
                try:
                    programar_notificaciones(ticket_id, new_asignado)
                except Exception as e:
                    print(f"[ERROR] Falló programar_notificaciones para {new_asignado}: {e}")
                    # No re-lanzamos para no abortar el update del ticket

        if "severidad" in updates:
            new_sev = updates["severidad"]
            new_sla = SLA_HORAS.get(new_sev, 72)
            new_prio = PRIORIDAD_MAP.get(new_sev, 3)
            new_vence = (datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(hours=new_sla)).isoformat()
            conn.execute(
                "UPDATE tickets SET prioridad = ?, sla_horas = ?, vence_at = ? WHERE id = ?",
                (new_prio, new_sla, new_vence, ticket_id)
            )
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, 'system', ?, ?)""",
                (ticket_id, f"[ESCALAMIENTO] Severidad cambiada a {new_sev}. Nuevo SLA: {new_sla}h", now)
            )

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


def reply_ticket_email(
    ticket_id: int,
    author_id: str,
    mensaje: str,
    asunto: Optional[str] = None,
    files: Optional[List[Any]] = None,  # List[UploadFile]
) -> Dict[str, Any]:
    """
    Envía respuesta por correo desde un ticket y mantiene hilo cuando existe email_thread_id.
    Registra historial en ticket_emails y evento en timeline.
    Soporta adjuntos.
    """
    import os
    import shutil
    from pathlib import Path

    ticket = get_ticket(ticket_id)
    if not ticket:
        logger.error(f"Reply failed: Ticket {ticket_id} not found")
        raise ValueError("Ticket no encontrado")

    clean_msg = (mensaje or "").strip()
    if not clean_msg:
        logger.error(f"Reply failed: Message empty for ticket {ticket_id}")
        raise ValueError("El mensaje de respuesta está vacío")

    _, parsed_addr = parseaddr(ticket.get("origen_email") or "")
    to_email = parsed_addr.strip() if parsed_addr else (ticket.get("origen_email") or "").strip()
    if not to_email or "@" not in to_email:
        logger.error(f"Reply failed: Invalid to_email '{to_email}' for ticket {ticket_id}")
        raise ValueError("Este ticket no tiene un correo de cliente válido")

    if asunto and asunto.strip():
        subject = asunto.strip()
    else:
        base = ticket.get("codigo") or f"Ticket #{ticket_id}"
        title = (ticket.get("titulo") or "").strip()
        subject = f"{base} - {title}" if title else base
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    thread_id = (ticket.get("email_thread_id") or "").strip()
    headers = {}
    if thread_id:
        headers["In-Reply-To"] = thread_id
        headers["References"] = thread_id

    escaped_msg = html.escape(clean_msg).replace("\n", "<br>")
    body_html = f"""
    <p>Hola,</p>
    <p>{escaped_msg}</p>
    <hr>
    <p style="color:#666;font-size:12px">
      Respuesta enviada desde Mesa de Ayuda {html.escape(ticket.get("codigo") or f"#{ticket_id}")}.
    </p>
    """
    now = db.now_utc_iso()
    preview = clean_msg if len(clean_msg) <= 300 else clean_msg[:300] + "..."
    
    # Procesar adjuntos
    email_attachments = []
    stored_attachments = []
    attachments_hash = ""
    
    if files:
        base_path = Path(app_settings.TICKET_ATTACHMENTS_DIR) / str(ticket_id) / "attachments"
        base_path.mkdir(parents=True, exist_ok=True)
        
        # Pre-calculated hash for dedupe
        import hashlib
        hasher = hashlib.md5()

        for file in files:
            try:
                # Validar tamaño y extensión
                file.file.seek(0, 2)
                size = file.file.tell()
                file.file.seek(0)
                
                if size > app_settings.TICKET_MAX_FILE_SIZE:
                    logger.warning(f"File {file.filename} exceeds max size")
                    continue
                    
                ext = Path(file.filename).suffix.lower()
                if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
                    logger.warning(f"File extension {ext} not allowed")
                    continue

                # Leer contenido
                file_content = file.file.read()
                hasher.update(file_content)
                hasher.update(file.filename.encode('utf-8'))

                # Guardar en disco (temporalmente, confirmaremos si no es duplicado)
                filename = getattr(file, "filename", "untitled")
                safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
                file_path = base_path / f"{int(datetime.utcnow().timestamp())}_{safe_filename}"
                
                with open(file_path, "wb") as f:
                    f.write(file_content)
                    
                email_attachments.append({
                    "filename": filename,
                    "data": file_content,
                    "content_type": getattr(file, "content_type", "application/octet-stream")
                })
                
                stored_attachments.append({
                    "filename": filename,
                    "path": str(file_path),
                    "size": len(file_content),
                    "content_type": getattr(file, "content_type", "application/octet-stream")
                })
            except Exception as e:
                logger.error(f"Error procesando adjunto {getattr(file, 'filename', '?')}: {e}")
        
        attachments_hash = hasher.hexdigest()

    dedupe_since = (
        datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(minutes=3)
    ).isoformat()
    marker_id = None

    # Lock + dedupe para evitar doble envío por reintento en UI.
    lock_conn = db.get_conn()
    try:
        try:
            lock_conn.execute("SELECT pg_advisory_lock(?)", (int(ticket_id),))
        except Exception:
            # Si no soporta advisory lock, seguimos con dedupe best-effort.
            pass

        # Check for duplicate including body and attachments hash (stored in metadata or body?)
        # For now, we trust subject + body + to_addr + strict time window.
        # Ideally we should store a hash of the operation.
        dup_row = lock_conn.execute(
            """SELECT id FROM ticket_emails
               WHERE ticket_id = ?
                 AND direction IN ('outgoing', 'outgoing_pending')
                 AND to_addr = ?
                 AND subject = ?
                 AND body_html = ?
                 AND created_at >= ?
               ORDER BY id DESC
               LIMIT 1""",
            (ticket_id, to_email, subject, body_html, dedupe_since),
        ).fetchone()
        
        if dup_row:
             # Clean up stored files as they are duplicates
            for att in stored_attachments:
                try:
                    Path(att["path"]).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to cleanup duplicate file {att['path']}: {e}")

            return {
                "ok": True,
                "ticket_id": ticket_id,
                "to_email": to_email,
                "subject": subject,
                "threaded": bool(thread_id),
                "duplicate_skipped": True,
                "message": "Se evitó un envío duplicado (correo ya enviado recientemente).",
            }

        marker_row = lock_conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, created_at)
               VALUES (?, 'outgoing_pending', '', ?, ?, ?, ?, ?)
               RETURNING id""",
            (ticket_id, to_email, subject, body_html, json.dumps(stored_attachments), now),
        ).fetchone()
        marker_id = marker_row["id"] if marker_row else None
        lock_conn.commit()
    finally:
        try:
            lock_conn.execute("SELECT pg_advisory_unlock(?)", (int(ticket_id),))
        except Exception:
            pass
        lock_conn.close()

    try:
        send_meta = email_sender.send_email_advanced(
            to_email=to_email,
            subject=subject,
            html_body=body_html,
            headers=headers or None,
            attachments=email_attachments
        )
    except Exception as e:
        # Limpieza de marcador para permitir retry real si falló envío.
        if marker_id:
            cleanup_conn = db.get_conn()
            try:
                cleanup_conn.execute(
                    "DELETE FROM ticket_emails WHERE id = ? AND direction = 'outgoing_pending'",
                    (marker_id,),
                )
                cleanup_conn.commit()
            finally:
                cleanup_conn.close()
        raise ValueError(str(e))

    conn = db.get_conn()
    try:
        if marker_id:
            conn.execute(
                """UPDATE ticket_emails
                   SET direction = 'outgoing', from_addr = ?
                   WHERE id = ?""",
                (send_meta.get("from_addr"), marker_id),
            )
        else:
            conn.execute(
                """INSERT INTO ticket_emails
                   (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    "outgoing",
                    send_meta.get("from_addr"),
                    to_email,
                    subject,
                    body_html,
                    json.dumps(stored_attachments),
                    now,
                ),
            )
        
        has_attachments = " (con adjuntos)" if stored_attachments else ""
        conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (ticket_id, author_id, f"[CORREO] Respuesta enviada a {to_email}{has_attachments}: {preview}", now),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))

        # Si el envío salió con Message-ID, lo usamos como referencia para próximos replies.
        msg_id = send_meta.get("message_id")
        if msg_id:
            # EN PROD EL MESSAGE-ID DEBERIA SER "FIJO" POR TICKET O ASOCIADO AL HILO
            # Pero por ahora mantenemos la lógica de actualizar con el último msg_id
            conn.execute("UPDATE tickets SET email_thread_id = ? WHERE id = ?", (msg_id, ticket_id))

        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "to_email": to_email,
        "subject": subject,
        "threaded": bool(thread_id),
        "message_id": send_meta.get("message_id"),
    }


def get_ticket_emails(ticket_id: int) -> List[Dict[str, Any]]:
    """Obtiene el historial de correos (entrantes y salientes) de un ticket."""
    conn = db.get_conn()
    try:
        cursor = conn.execute(
            """SELECT * FROM ticket_emails 
               WHERE ticket_id = ? 
               ORDER BY created_at DESC""",
            (ticket_id,)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_timeline(ticket_id: int, limit: int = 120) -> List[Dict[str, Any]]:
    """Línea de tiempo unificada para la UI."""
    conn = db.get_conn()
    try:
        limit = max(1, min(int(limit or 120), 500))
        cursor = conn.execute(
            "SELECT * FROM ticket_comments WHERE ticket_id = ? ORDER BY created_at DESC LIMIT ?",
            (ticket_id, limit)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            content = r["content"]
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
            "by_category": {},
            "pivot_assignee": {},
            "sla_compliance": {"on_time": 0, "breached": 0},
            "total": 0,
        }

        # Por Estado
        rows = conn.execute("SELECT estado, COUNT(*) as c FROM tickets GROUP BY estado").fetchall()
        for r in rows:
            stats["by_status"][r["estado"]] = r["c"]
            stats["total"] += r["c"]

        # Por Severidad
        rows = conn.execute("SELECT severidad, COUNT(*) as c FROM tickets GROUP BY severidad").fetchall()
        for r in rows:
            stats["by_prio"][r["severidad"]] = r["c"]

        # Por Categoría
        rows = conn.execute("SELECT categoria, COUNT(*) as c FROM tickets GROUP BY categoria").fetchall()
        for r in rows:
            stats["by_category"][r["categoria"] or "general"] = r["c"]

        # Pivot: Assignee vs Status
        rows = conn.execute(
            "SELECT asignado_a, estado, COUNT(*) as c FROM tickets GROUP BY asignado_a, estado"
        ).fetchall()
        for r in rows:
            assignee = r["asignado_a"] or "Sin Asignar"
            status = r["estado"]
            count = r["c"]
            if assignee not in stats["pivot_assignee"]:
                stats["pivot_assignee"][assignee] = {"total": 0}
            stats["pivot_assignee"][assignee][status] = count
            stats["pivot_assignee"][assignee]["total"] += count

        # SLA Compliance
        now = db.now_utc_iso()
        row = conn.execute("""
            SELECT
                COUNT(CASE WHEN vence_at >= ? OR estado IN ('cerrado','resuelto') THEN 1 END) as on_time,
                COUNT(CASE WHEN vence_at < ? AND estado NOT IN ('cerrado','resuelto') THEN 1 END) as breached
            FROM tickets WHERE vence_at IS NOT NULL
        """, (now, now)).fetchone()
        if row:
            stats["sla_compliance"]["on_time"] = row["on_time"]
            stats["sla_compliance"]["breached"] = row["breached"]

        return stats
    finally:
        conn.close()


# ==========================================================================
# GESTIÓN DE ESPECIALIDADES
# ==========================================================================
def list_specialties() -> List[Dict[str, Any]]:
    """Lista todas las especialidades de usuarios."""
    conn = db.get_conn()
    try:
        rows = conn.execute("""
            SELECT us.*, u.role
            FROM user_specialties us
            LEFT JOIN users u ON u.username = us.username
            ORDER BY us.specialty, us.username
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def upsert_specialty(username: str, specialty: str, max_load: int = 10) -> Dict[str, Any]:
    """Crear o actualizar especialidad de usuario."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute("""
            INSERT INTO user_specialties (username, specialty, max_load, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(username, specialty) DO UPDATE SET
                max_load = excluded.max_load,
                updated_at = excluded.updated_at
        """, (username, specialty, max_load, now, now))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_specialties WHERE username = ? AND specialty = ?",
            (username, specialty)
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def toggle_availability(username: str, is_available: bool) -> None:
    """Activar/desactivar disponibilidad de un técnico."""
    conn = db.get_conn()
    try:
        conn.execute("""
            UPDATE user_specialties
            SET is_available = ?, updated_at = ?
            WHERE username = ?
        """, (1 if is_available else 0, db.now_utc_iso(), username))
        conn.commit()
    finally:
        conn.close()


def delete_specialty(username: str, specialty: str) -> None:
    """Eliminar una especialidad de un técnico."""
    conn = db.get_conn()
    try:
        conn.execute(
            "DELETE FROM user_specialties WHERE username = ? AND specialty = ?",
            (username, specialty)
        )
        conn.commit()
    finally:
        conn.close()


# ==========================================================================
# PROCESAMIENTO DE CORREOS (INCOMING)
# ==========================================================================
def _extract_message_ids(raw_header: str) -> List[str]:
    if not raw_header:
        return []
    found = re.findall(r"<[^>]+>", raw_header)
    if found:
        return found
    return [p.strip() for p in raw_header.split() if p.strip()]


def _message_id_variants(message_id: str) -> List[str]:
    raw = (message_id or "").strip()
    if not raw:
        return []
    core = raw.strip("<>").strip()
    variants = [raw]
    if core:
        if core not in variants:
            variants.append(core)
        bracketed = f"<{core}>"
        if bracketed not in variants:
            variants.append(bracketed)
    return variants


def _find_ticket_by_thread_headers(in_reply_to: str, references: str) -> Optional[int]:
    conn = db.get_conn()
    try:
        candidates = []
        candidates.extend(_extract_message_ids(in_reply_to))
        candidates.extend(_extract_message_ids(references))
        for candidate in candidates:
            for token in _message_id_variants(candidate):
                row = conn.execute(
                    "SELECT id FROM tickets WHERE email_thread_id = ? ORDER BY id DESC LIMIT 1",
                    (token,),
                ).fetchone()
                if row:
                    return int(row["id"])
        return None
    finally:
        conn.close()


def _find_ticket_by_subject(subject: str) -> Optional[int]:
    conn = db.get_conn()
    try:
        # Formato actual: TK-DD-MM-YYYY-NNNN
        # Formato legacy: TK-YYYYMM-NNNN
        for pattern in (
            r"(TK-\d{2}-\d{2}-\d{4}-\d{4,})",
            r"(TK-\d{6}-\d{4,})",
        ):
            code_match = re.search(pattern, subject or "", re.IGNORECASE)
            if code_match:
                code = code_match.group(1).upper()
                row = conn.execute(
                    "SELECT id FROM tickets WHERE UPPER(codigo) = UPPER(?) ORDER BY id DESC LIMIT 1",
                    (code,),
                ).fetchone()
                if row:
                    return int(row["id"])

        # Fallback legacy: TK-1234 (id directo).
        legacy_match = re.search(r"TK-(\d+)", subject or "", re.IGNORECASE)
        if legacy_match:
            row = conn.execute("SELECT id FROM tickets WHERE id = ?", (int(legacy_match.group(1)),)).fetchone()
            if row:
                return int(row["id"])
        return None
    finally:
        conn.close()


def handle_incoming_email(msg: Dict[str, Any]) -> None:
    """
    Procesa un mensaje de correo entrante.
    Priorización:
    1) Match por hilo (In-Reply-To / References).
    2) Match por código en asunto (TK-DD-MM-YYYY-NNNN, legacy TK-YYYYMM-NNNN o TK-1234).
    3) Si no hay match, crea ticket nuevo.
    """
    subject = msg.get("subject", "")
    sender = msg.get("sender", "")
    body = msg.get("body", "")
    msg_id = msg.get("message_id", "")
    in_reply_to = msg.get("in_reply_to", "")
    references = msg.get("references", "")

    try:
        ticket_id = _find_ticket_by_thread_headers(in_reply_to, references)
        if ticket_id:
            _process_reply_email(ticket_id, sender, subject, body, msg_id)
            return
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by thread headers: {e}")

    try:
        ticket_id = _find_ticket_by_subject(subject)
        if ticket_id:
            _process_reply_email(ticket_id, sender, subject, body, msg_id)
            return
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by subject: {e}")

    _process_new_email_ticket(subject, sender, body, msg_id)


def _process_reply_email(ticket_id: int, sender: str, subject: str, body: str, msg_id: str):
    print(f"[EMAIL] Reply to Ticket #{ticket_id} from {sender}")
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        preview = (body or "").strip()
        if len(preview) > 600:
            preview = preview[:600] + "..."

        conn.execute(
            "INSERT INTO ticket_comments (ticket_id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, f"email:{sender}", f"[CORREO_ENTRANTE] {preview}", now)
        )
        conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket_id,
                "incoming",
                sender,
                "",
                subject or "",
                html.escape(body or "").replace("\n", "<br>"),
                "[]",
                now,
            ),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        if msg_id:
            conn.execute("UPDATE tickets SET email_thread_id = ? WHERE id = ?", (msg_id, ticket_id))
        conn.commit()
    finally:
        conn.close()


def _process_new_email_ticket(subject: str, sender: str, body: str, msg_id: str):
    print(f"[EMAIL] New Ticket from {sender}")
    
    # 1. Clasificación
    categoria = clasificar_ticket(subject, body)
    
    # 2. Triaje (Mesa vs Especialista)
    asignado_a = None
    if categoria == "general":
        asignado_a = "mesa_ayuda" 
    else:
        asignado_a = auto_asignar(categoria)
        if not asignado_a:
            asignado_a = "mesa_ayuda"

    # 3. Datos del cliente
    cliente_nombre = sender
    origen_email = sender
    if "<" in sender:
        parts = sender.split("<")
        cliente_nombre = parts[0].strip().replace('"', '')
        origen_email = parts[1].strip().replace('>', '')

    conn = None
    now = db.now_utc_iso()

    # 4. Crear Ticket
    try:
        tk = create_ticket(
            titulo=subject,
            descripcion=body,
            creador_id="email_bot",
            categoria=categoria,
            origen_email=origen_email,
            cliente_nombre=cliente_nombre,
            email_thread_id=msg_id
        )
        
        ticket_id = tk['id']
        codigo = tk['codigo']
        
        # Override asignado_a if manual triage set it to Mesa
        if asignado_a == "mesa_ayuda" and tk.get("asignado_a") != "mesa_ayuda":
             # create_ticket might have auto-assigned. Does create_ticket handle "Mesa"?
             # auto_asignar in create_ticket returns a tech username or None.
             # If create_ticket found someone, we keep it. 
             # But if our triage said "mesa_ayuda" because category is "general", create_ticket might have assigned to a general tech?
             # Let's trust create_ticket's auto-assignment logic unless we strictly want Mesa.
             # If category is general, create_ticket calls auto_asignar(general).
             # If we want to force Mesa for general, we should update it.
             pass
             
        if asignado_a == "mesa_ayuda":
             update_ticket(ticket_id, {"asignado_a": "mesa_ayuda"})
             # Re-fetch to confirm?
             # tk['asignado_a'] = "mesa_ayuda"

        # Registrar correo entrante en historial de correos.
        conn = db.get_conn()
        conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket_id,
                "incoming",
                sender,
                "",
                subject or "",
                html.escape(body or "").replace("\n", "<br>"),
                "[]",
                now,
            ),
        )
        conn.commit()

        print(f"[EMAIL] Created Ticket {codigo} (#{ticket_id})")

        # 5. Programar Auto-Respuesta (DESACTIVADO TEMPORALMENTE - CUENTA PERSONAL)
        # Cuando se migre a una cuenta dedicada (ej: soporte@...), descomentar esto.
        # 5. Programar Auto-Respuesta
        if app_settings.TICKET_AUTO_REPLY_ENABLED:
            payload = json.dumps({
                "ticket_id": ticket_id,
                "email": origen_email,
                "nombre": cliente_nombre,
                "asignado_a": asignado_a
            })
            run_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            
            conn.execute(
                "INSERT INTO sys_jobs (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at) VALUES (?, 'PENDING', ?, ?, 0, 3, ?, ?)",
                ("SEND_AUTO_RESPONSE", payload, run_at, now, now)
            )
            conn.commit()
            print(f"[EMAIL] Auto-response scheduled for TK-{ticket_id} in 15m")

    except Exception as e:
        logger.error(f"[EMAIL] Error creating ticket: {e}")
    finally:
        if conn:
            conn.close()
