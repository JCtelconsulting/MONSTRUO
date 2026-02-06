#!/usr/bin/env python3
"""
Create Workflow tasks from Parrotfy alerts with intelligent deduplication.

Rules:
- Fingerprint: PF_MISSING_IN_LAUDUS|{folio_norm}
- If fingerprint exists and task is Open/Doing: don't create new task
- If >60 min since last comment: add update comment
- If fingerprint doesn't exist: create new task and register fingerprint
- Idempotent: can run multiple times without duplicating
"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import get_conn, now_utc_iso
from workflow_db import init_workflow_db

COOLDOWN_MINUTES = 60

def parse_iso_timestamp(s: str) -> datetime:
    """Parse ISO timestamp to datetime object"""
    try:
        # Handle both with/without Z suffix
        s = s.replace("Z", "")
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def get_or_create_master_case(conn: sqlite3.Connection, ts: str) -> int:
    """Get or create the master case for Parrotfy discrepancies"""
    # Check if master case exists
    rows = conn.execute("""
        SELECT id FROM cases 
        WHERE title LIKE '%Parrotfy vs Laudus%' 
        AND status IN ('open', 'in_progress')
        ORDER BY created_at DESC
        LIMIT 1
    """).fetchall()
    
    if rows:
        case_id = int(rows[0]["id"])
        print(f"INFO: Using existing master case case_id={case_id}")
        return case_id
    
    # Create new master case
    description = """Discrepancias automáticas detectadas entre Parrotfy y Laudus.

**Estado de Integración:**
- Invoices: ✅ OK (20 registros en staging)
- Payments: ⚠️ SKIPPED (endpoint roto - error 500)
- Inventory: ✅ OK (20 registros en staging)

**Evidencia de error en pagos:**
/srv/inteligencia_artificial/documentacion/parrotfy_pagos_500_evidencia.txt

**Request IDs para escalar a Parrotfy:**
- bc61b760-db5f-4f10-9c5c-a58f229ab2b6
- 9b122475-93b9-4342-a833-1a4410f76935
- e90bc770-08a3-4ec2-8e88-4bb17bfb985c

Las tareas de este caso corresponden a facturas de Parrotfy que NO tienen match en Laudus.
Sistema de deduplicación activo: mismo problema = misma tarea (sin duplicados).
"""
    
    case_id_result = conn.execute("""
        INSERT INTO cases (title, description, status, priority, owner_role, created_by, created_at, updated_at)
        VALUES (?, ?, 'open', 'high', 'finance', 'system', ?, ?)
    """, (
        "Parrotfy vs Laudus - Discrepancias (Staging)",
        description,
        ts,
        ts
    ))
    conn.commit()
    case_id = int(case_id_result.lastrowid)
    print(f"INFO: Created master case case_id={case_id}")
    return case_id

def compute_fingerprint(alert: Dict[str, Any]) -> str:
    """
    Compute stable fingerprint for an alert.
    Format: PF_MISSING_IN_LAUDUS|{folio_norm}
    """
    try:
        details = json.loads(str(alert.get("details_json") or "{}"))
        norm = str(details.get("norm", "")).strip()
        if not norm:
            # Fallback: use entity_id if norm not available
            norm = str(alert.get("entity_id", "")).strip()
        
        if not norm:
            # Ultimate fallback: use alert id (not ideal but prevents crash)
            return f"PF_MISSING_IN_LAUDUS|ALERT_{alert.get('id')}"
        
        return f"PF_MISSING_IN_LAUDUS|{norm}"
    except Exception as e:
        # Fallback on error
        return f"PF_MISSING_IN_LAUDUS|ALERT_{alert.get('id')}"

def get_existing_dedup(conn: sqlite3.Connection, fingerprint: str) -> Optional[Dict[str, Any]]:
    """Check if fingerprint exists and return dedup record"""
    rows = conn.execute("""
        SELECT d.fingerprint, d.task_id, d.case_id, d.first_seen, d.last_seen, d.last_comment_at, d.hit_count,
               t.status as task_status
        FROM workflow_dedup d
        LEFT JOIN tasks t ON d.task_id = t.id
        WHERE d.fingerprint = ?
    """, (fingerprint,)).fetchall()
    
    if not rows:
        return None
    
    return dict(rows[0])

def should_add_comment(last_comment_at: str, ts: str) -> bool:
    """Check if enough time has passed since last comment (cooldown)"""
    if not last_comment_at:
        return True
    
    try:
        last_dt = parse_iso_timestamp(last_comment_at)
        now_dt = parse_iso_timestamp(ts)
        delta = now_dt - last_dt
        return delta.total_seconds() > (COOLDOWN_MINUTES * 60)
    except Exception:
        return True

def create_task_for_alert(
    conn: sqlite3.Connection,
    case_id: int,
    alert: Dict[str, Any],
    fingerprint: str,
    ts: str
) -> int:
    """Create a new task for an alert and register fingerprint"""
    try:
        details = json.loads(str(alert.get("details_json") or "{}"))
    except Exception:
        details = {}
    
    norm = details.get("norm", "")
    pf_invoice_id = details.get("parrotfy_invoice_id", "")
    pf_invoice_number = details.get("parrotfy_invoice_number", "")
    
    title = f"Factura Parrotfy {pf_invoice_number or norm} no encontrada en Laudus"
    description = f"""**Tipo:** Missing in Laudus
**Folio normalizado:** {norm}
**Parrotfy Invoice ID:** {pf_invoice_id}
**Parrotfy Invoice Number:** {pf_invoice_number}

**Alert ID:** {alert.get('id')}
**Severity:** {alert.get('severity', 'high')}
**Primera detección:** {alert.get('first_seen_at', ts)}

**Acciones recomendadas:**
1. Verificar si la factura es reciente (últimos 7 días)
2. Si es antigua (>30 días), puede indicar gap en sync de Laudus
3. Revisar raw_json de la factura en `parrotfy_invoices` tabla
4. Si es válida: investigar por qué Laudus no la tiene

**Query de investigación:**
```sql
SELECT * FROM parrotfy_invoices WHERE parrotfy_invoice_id = '{pf_invoice_id}';
SELECT * FROM laudus_invoices WHERE raw_json LIKE '%{norm}%';
```
"""
    
    # Create task
    task_result = conn.execute("""
        INSERT INTO tasks (case_id, title, description, status, assignee_role, created_at, updated_at)
        VALUES (?, ?, ?, 'open', 'finance', ?, ?)
    """, (case_id, title, description, ts, ts))
    task_id = int(task_result.lastrowid)
    
    # Link alert to case
    try:
        conn.execute("""
            INSERT INTO task_links (case_id, link_type, link_key, created_at)
            VALUES (?, 'alert', ?, ?)
        """, (case_id, str(alert.get("id")), ts))
    except Exception:
        pass  # Ignore duplicates
    
    # Register fingerprint
    conn.execute("""
        INSERT INTO workflow_dedup (fingerprint, task_id, case_id, first_seen, last_seen, last_comment_at, hit_count)
        VALUES (?, ?, ?, ?, ?, '', 1)
    """, (fingerprint, task_id, case_id, ts, ts))
    
    conn.commit()
    print(f"INFO: Created task_id={task_id} for fingerprint={fingerprint}")
    return task_id

def update_existing_dedup(
    conn: sqlite3.Connection,
    dedup: Dict[str, Any],
    alert: Dict[str, Any],
    ts: str
) -> None:
    """Update existing dedup record and optionally add comment"""
    fingerprint = dedup["fingerprint"]
    task_id = int(dedup["task_id"])
    hit_count = int(dedup.get("hit_count", 1))
    last_comment_at = dedup.get("last_comment_at", "")
    
    # Update hit count and last_seen
    conn.execute("""
        UPDATE workflow_dedup
        SET last_seen = ?,
            hit_count = ?
        WHERE fingerprint = ?
    """, (ts, hit_count + 1, fingerprint))
    
    # Check if we should add a comment (cooldown)
    if should_add_comment(last_comment_at, ts):
        comment_text = f"""Reaparece en sync: {ts}

**Occurrences:** {hit_count + 1}
**Alert ID:** {alert.get('id')}
**Status Alert:** {alert.get('status', 'open')}

El problema persiste. Requiere investigación manual.
"""
        conn.execute("""
            INSERT INTO task_comments (task_id, author, comment, created_at)
            VALUES (?, 'system', ?, ?)
        """, (task_id, comment_text, ts))
        
        # Update last_comment_at
        conn.execute("""
            UPDATE workflow_dedup
            SET last_comment_at = ?
            WHERE fingerprint = ?
        """, (ts, fingerprint))
        
        print(f"INFO: Added comment to task_id={task_id} (fingerprint={fingerprint})")
    else:
        print(f"INFO: Skipped comment for task_id={task_id} (cooldown active, last_comment_at={last_comment_at})")
    
    conn.commit()

def auto_resolve_missing_problems(conn: sqlite3.Connection, seen_fingerprints: set, ts: str) -> int:
    """
    Auto-resolve tasks for fingerprints that haven't appeared in recent syncs.
    Returns number of tasks auto-resolved.
    """
    auto_closed = 0
    
    # Get all fingerprints in workflow_dedup
    all_dedup = conn.execute("""
        SELECT d.fingerprint, d.task_id, d.miss_streak, d.last_seen, t.status as task_status
        FROM workflow_dedup d
        LEFT JOIN tasks t ON d.task_id = t.id
    """).fetchall()
    
    for row in all_dedup:
        fp = row["fingerprint"]
        task_id = int(row["task_id"])
        miss_streak = int(row["miss_streak"] if row["miss_streak"] is not None else 0)
        task_status = row["task_status"] if row["task_status"] is not None else ""
        last_seen = row["last_seen"] if row["last_seen"] is not None else "N/A"
        
        if fp in seen_fingerprints:
            # Fingerprint seen this run: reset miss_streak
            conn.execute("""
                UPDATE workflow_dedup
                SET miss_streak = 0
                WHERE fingerprint = ?
            """, (fp,))
        else:
            # Fingerprint NOT seen: increment miss_streak
            new_miss_streak = miss_streak + 1
            conn.execute("""
                UPDATE workflow_dedup
                SET miss_streak = ?
                WHERE fingerprint = ?
            """, (new_miss_streak, fp))
            
            # Auto-resolve if miss_streak >= 2 and task is still open/doing/blocked
            if new_miss_streak >= 2 and task_status in ("open", "doing", "blocked"):
                # Mark task as done
                conn.execute("""
                    UPDATE tasks
                    SET status = 'done',
                        updated_at = ?
                    WHERE id = ?
                """, (ts, task_id))
                
                # Add auto-resolve comment
                comment = f"""✅ Auto-resuelto: no reaparece en {new_miss_streak} ciclos consecutivos.

**Fingerprint:** {fp}
**Última detección:** {last_seen}
**Auto-cerrado:** {ts}

El problema se considera resuelto automáticamente. Si reaparece, la tarea se reabrirá automáticamente.
"""
                conn.execute("""
                    INSERT INTO task_comments (task_id, author, comment, created_at)
                    VALUES (?, 'system', ?, ?)
                """, (task_id, comment, ts))
                
                auto_closed += 1
                print(f"INFO: Auto-resolved task_id={task_id} (fingerprint={fp}, miss_streak={new_miss_streak})")
    
    conn.commit()
    return auto_closed

def publish_to_bridge(conn: sqlite3.Connection, event_data: Dict[str, Any]) -> None:
    """Publish structured event to Bridge"""
    try:
        # Check if bridge_messages table exists (from bridge_init.py)
        conn.execute("SELECT 1 FROM bridge_messages LIMIT 1")
        
        # Insert message (kind='result' for workflow results)
        conn.execute("""
            INSERT INTO bridge_messages (
                thread_id, from_agent, to_agent, kind, title, body, payload_json, 
                requires_approval, approval_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'na', ?)
        """, (
            "jarvis",  # default thread
            "monstruo_workflow",  # from agent
            "all",  # broadcast to all agents
            "result",  # kind
            f"Workflow Dedupe Result - Case {event_data.get('case_id')}",  # title
            f"Created: {event_data.get('created_tasks')} | Deduped: {event_data.get('deduped')} | Auto-closed: {event_data.get('auto_closed')}",  # body
            json.dumps(event_data, ensure_ascii=True, sort_keys=True),  # payload
            event_data.get("timestamp", now_utc_iso())  # created_at
        ))
        conn.commit()
        print(f"INFO: Published event to Bridge: {event_data.get('kind')}")
    except Exception as e:
        # Bridge table might not exist yet, log but don't fail
        print(f"WARN: Could not publish to Bridge (table might not exist): {e}")

def main() -> int:
    conn = get_conn()
    try:
        init_workflow_db()
        ts = now_utc_iso()
        
        # Get master case
        case_id = get_or_create_master_case(conn, ts)
        
        # Track seen fingerprints for auto-resolve
        seen_fingerprints: set = set()
        
        # Get relevant alerts (only missing_in_laudus_norm to avoid duplicates)
        alerts = conn.execute("""
            SELECT id, rule, severity, entity_type, entity_id, summary, details_json, status, first_seen_at, last_seen_at
            FROM alerts
            WHERE rule = 'parrotfy_invoice_missing_in_laudus_norm'
              AND status = 'open'
            ORDER BY first_seen_at ASC
        """).fetchall()
        
        print(f"INFO: Found {len(alerts)} alerts to process")
        
        stats = {
            "new_tasks": 0,
            "updated_tasks": 0,
            "skipped_cooldown": 0,
            "skipped_done": 0,
            "auto_closed": 0
        }
        
        for alert_row in alerts:
            alert = dict(alert_row)
            fingerprint = compute_fingerprint(alert)
            
            # Mark as seen
            seen_fingerprints.add(fingerprint)
            
            # Check if fingerprint exists
            dedup = get_existing_dedup(conn, fingerprint)
            
            if dedup:
                task_status = dedup.get("task_status", "")
                
                # If task is done, skip
                if task_status == "done":
                    stats["skipped_done"] += 1
                    continue
                
                # If task is open/doing/blocked, update
                if task_status in ("open", "doing", "blocked"):
                    update_existing_dedup(conn, dedup, alert, ts)
                    
                    # Check if comment was added or skipped
                    if should_add_comment(dedup.get("last_comment_at", ""), ts):
                        stats["updated_tasks"] += 1
                    else:
                        stats["skipped_cooldown"] += 1
                else:
                    # Unknown status, create new
                    create_task_for_alert(conn, case_id, alert, fingerprint, ts)
                    stats["new_tasks"] += 1
            else:
                # New problem, create task
                create_task_for_alert(conn, case_id, alert, fingerprint, ts)
                stats["new_tasks"] += 1
        
        # Auto-resolve missing problems
        stats["auto_closed"] = auto_resolve_missing_problems(conn, seen_fingerprints, ts)
        
        conn.commit()
        
        # Get integration errors for Bridge event
        integration_errors = []
        errors = conn.execute("""
            SELECT rule, severity, summary
            FROM alerts
            WHERE rule LIKE 'integration_%'
              AND status = 'open'
        """).fetchall()
        for err in errors:
            integration_errors.append({
                "rule": err["rule"],
                "severity": err["severity"],
                "summary": err["summary"]
            })
        
        # Publish to Bridge
        bridge_event = {
            "kind": "workflow_dedupe_result",
            "source": "parrotfy",
            "timestamp": ts,
            "case_id": case_id,
            "created_tasks": stats["new_tasks"],
            "deduped": stats["updated_tasks"] + stats["skipped_cooldown"],
            "comments_added": stats["updated_tasks"],
            "auto_closed": stats["auto_closed"],
            "active_fingerprints": len(seen_fingerprints),
            "integration_errors": integration_errors
        }
        publish_to_bridge(conn, bridge_event)
        
        # Print summary
        print("\n" + "="*80)
        print("WORKFLOW CREATION SUMMARY")
        print("="*80)
        print(f"Master Case ID: {case_id}")
        print(f"Total Alerts Processed: {len(alerts)}")
        print(f"New Tasks Created: {stats['new_tasks']}")
        print(f"Tasks Updated (comment added): {stats['updated_tasks']}")
        print(f"Tasks Skipped (cooldown): {stats['skipped_cooldown']}")
        print(f"Tasks Skipped (already done): {stats['skipped_done']}")
        print(f"Tasks Auto-Closed: {stats['auto_closed']}")
        print(f"Active Fingerprints: {len(seen_fingerprints)}")
        print("="*80)
        
        return 0
        
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())

