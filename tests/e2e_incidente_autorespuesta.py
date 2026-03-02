#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path
import sys

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
CODE_ROOT = PROJECT_ROOT / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.core import db, jobs_engine, tickets_service, email
from app.core.config import settings


def setup_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT,
            name TEXT,
            email TEXT
        );

        CREATE TABLE IF NOT EXISTS ticket_config_client_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            customer_id TEXT,
            customer_name TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            titulo TEXT,
            descripcion TEXT,
            estado TEXT,
            severidad TEXT,
            tipo TEXT,
            creador_id TEXT,
            asignado_a TEXT,
            vence_at TEXT,
            created_at TEXT,
            updated_at TEXT,
            categoria TEXT,
            origen_email TEXT,
            cliente_nombre TEXT,
            prioridad INTEGER,
            sla_horas INTEGER,
            email_thread_id TEXT,
            email_references TEXT,
            ticket_security_class TEXT,
            retention_days_snapshot INTEGER,
            subestado TEXT,
            frt_due_at TEXT,
            ttr_due_at TEXT,
            first_response_at TEXT,
            resolved_at TEXT,
            closed_at TEXT,
            frt_breached_at TEXT,
            ttr_breached_at TEXT,
            sla_mode_snapshot TEXT,
            escalation_window_hours_snapshot INTEGER,
            customer_id TEXT,
            contact_role TEXT,
            notify_emails TEXT
        );

        CREATE TABLE IF NOT EXISTS ticket_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            user_id TEXT,
            content TEXT,
            is_internal INTEGER DEFAULT 0,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ticket_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            from_subestado TEXT,
            to_subestado TEXT,
            actor TEXT,
            reason TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ticket_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            event_type TEXT,
            payload TEXT,
            actor TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ticket_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            direction TEXT,
            from_addr TEXT,
            to_addr TEXT,
            subject TEXT,
            body_html TEXT,
            attachments_json TEXT,
            idempotency_key TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sys_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT,
            status TEXT,
            payload TEXT,
            next_run_at TEXT,
            retries_count INTEGER,
            max_retries INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    conn.execute("INSERT OR REPLACE INTO system_settings(key, value) VALUES('ticket_auto_reply_enabled', 'true')")
    conn.commit()


def main() -> int:
    db_file = tempfile.NamedTemporaryFile(prefix="e2e_ticket_", suffix=".sqlite", delete=False)
    db_path = db_file.name
    db_file.close()

    def _dict_factory(cursor, row):
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

    def _get_conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = _dict_factory
        return conn

    db.get_conn = _get_conn  # type: ignore

    conn = _get_conn()
    setup_schema(conn)
    conn.close()

    settings.TICKET_AUTO_REPLY_ENABLED = True
    settings.TICKET_AUTO_REPLY_DELAY_MINUTES = 0
    settings.TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS = "noreply,no-reply,mailer-daemon,postmaster"

    def _fake_send_email_advanced(to_email: str, subject: str, html_body: str, headers=None, attachments=None):
        return {
            "ok": True,
            "from_addr": "soporte@monstruo.local",
            "message_id": f"<auto-{to_email}>",
        }

    email.send_email_advanced = _fake_send_email_advanced  # type: ignore

    results = []

    for i in range(1, 6):
        sender = f"cliente{i}@example.com"
        tickets_service._process_new_email_ticket(
            subject=f"Incidente E2E #{i}",
            sender=sender,
            body="Falla en servicio.",
            msg_id=f"<msg-{i}@example.com>",
            in_reply_to=None,
            references=None,
            attachments=[],
        )

        conn = _get_conn()
        try:
            t = conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 1").fetchone()
            ticket_id = int(t["id"])

            bad_auto_assign = t["asignado_a"] is not None

            job = conn.execute(
                "SELECT id, payload FROM sys_jobs WHERE job_type='SEND_AUTO_RESPONSE' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            payload = json.loads(job["payload"])
        finally:
            conn.close()

        asyncio.run(jobs_engine.send_auto_response_job(payload))

        conn = _get_conn()
        try:
            sent = conn.execute(
                "SELECT to_addr FROM ticket_emails WHERE ticket_id=? AND direction='auto_reply' ORDER BY id DESC LIMIT 1",
                (ticket_id,),
            ).fetchone()
            sent_ok = bool(sent and str(sent["to_addr"]).lower() == sender)

            internal_notes = conn.execute(
                "SELECT content, is_internal FROM ticket_comments WHERE ticket_id=? ORDER BY id ASC",
                (ticket_id,),
            ).fetchall()
            note_ok = any(
                int(r["is_internal"] or 0) == 1
                and "Estado:" in str(r["content"])
                and "Motivo:" in str(r["content"])
                for r in internal_notes
            )

            results.append(
                {
                    "caso": i,
                    "ticket_id": ticket_id,
                    "auto_asignacion_indebida": bad_auto_assign,
                    "auto_respuesta_entregada": sent_ok,
                    "nota_interna_completa": note_ok,
                }
            )
        finally:
            conn.close()

    print("caso|ticket|auto_asignacion_indebida|auto_respuesta_entregada|nota_interna_completa")
    for r in results:
        print(
            f"{r['caso']}|{r['ticket_id']}|{r['auto_asignacion_indebida']}|"
            f"{r['auto_respuesta_entregada']}|{r['nota_interna_completa']}"
        )

    bad_assign = sum(1 for r in results if r["auto_asignacion_indebida"])
    ok_reply = sum(1 for r in results if r["auto_respuesta_entregada"])
    ok_notes = sum(1 for r in results if r["nota_interna_completa"])

    print(f"SUMMARY bad_assign={bad_assign} ok_reply={ok_reply}/5 ok_notes={ok_notes}/5")

    if bad_assign == 0 and ok_reply == 5 and ok_notes == 5:
        print("PASS")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
