#!/usr/bin/env python3
from __future__ import annotations

import base64
import sys
import unittest
from datetime import datetime
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import MagicMock, patch

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
CODE_ROOT = PROJECT_ROOT / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.core.tickets import roles as ticket_roles
from app.core.tickets import workflow as ticket_workflow
from app.core import email_integration
from app.core import tickets_service


class TicketRolesPolicyTests(unittest.TestCase):
    def test_admin_is_not_tech_execution_role(self) -> None:
        self.assertTrue(ticket_roles.is_admin_management_role("admin"))
        self.assertFalse(ticket_roles.is_tech_execution_role("admin"))

    def test_admin_cannot_participate_even_if_assigned(self) -> None:
        ticket = {"asignado_a": "alice"}
        self.assertFalse(ticket_roles.can_participate(ticket, "alice", "admin"))
        with self.assertRaises(PermissionError):
            ticket_roles.require_can_participate(ticket, "alice", "admin", "agregar notas")

    def test_admin_with_tech_secondary_can_participate_if_assigned(self) -> None:
        ticket = {"asignado_a": "alice"}
        roles = ["admin", "sistemas"]
        self.assertTrue(ticket_roles.can_participate(ticket, "alice", roles))
        ticket_roles.require_can_participate(ticket, "alice", roles, "agregar notas")

    def test_non_assignee_tech_cannot_manage(self) -> None:
        ticket = {"asignado_a": "alice"}
        self.assertFalse(ticket_roles.can_manage(ticket, "bob", "sistemas"))
        with self.assertRaises(PermissionError):
            ticket_roles.require_can_manage(ticket, "bob", "sistemas", "cambiar estado")

    def test_tickets_service_wrappers_follow_same_policy(self) -> None:
        ticket = {"asignado_a": "alice"}
        self.assertFalse(tickets_service._is_tech_role("admin"))
        self.assertTrue(tickets_service._is_admin_management_role("admin"))
        with self.assertRaises(PermissionError):
            tickets_service._ensure_can_participate_ticket(ticket, "alice", "admin", "responder correos")


class TicketWorkflowPolicyTests(unittest.TestCase):
    def test_normalize_transition_target_legacy_triage(self) -> None:
        self.assertEqual(
            ticket_workflow.normalize_transition_target("recibido", "triage"),
            "asignado",
        )
        self.assertEqual(
            ticket_workflow.normalize_transition_target("asignado", "triage"),
            "asignado",
        )

    def test_workflow_transition_reopen_is_supported(self) -> None:
        self.assertTrue(ticket_workflow.can_transition("incidencia", "cerrado", "reabierto"))
        self.assertTrue(ticket_workflow.can_transition("requerimiento", "resuelto", "reabierto"))
        self.assertTrue(ticket_workflow.can_transition("cambio", "resuelto", "reabierto"))

    def test_workflow_legacy_direct_close_from_validation(self) -> None:
        self.assertTrue(ticket_workflow.can_transition("requerimiento", "en_validacion", "cerrado"))
        self.assertTrue(ticket_workflow.can_transition("cambio", "en_validacion", "cerrado"))


class TicketTimelineTests(unittest.TestCase):
    @staticmethod
    def _assert_iso8601(value: str) -> None:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        assert parsed is not None

    def test_get_timeline_includes_non_null_iso_timestamps_and_consistent_order(self) -> None:
        rows = [
            {
                "id": 1,
                "user_id": "tecnico1",
                "content": "[TRANSICION] asignado -> en_progreso",
                "created_at": "2026-02-26T21:02:11+00:00",
            },
            {
                "id": 2,
                "user_id": "cliente1",
                "content": "Cliente aporta más contexto",
                "created_at": "2026-02-26T21:01:05+00:00",
            },
        ]

        mock_conn = MagicMock()
        # 4 queries: comments, transitions, approvals, (emails only if include_emails)
        comment_cursor = MagicMock(); comment_cursor.fetchall.return_value = rows
        empty_cursor = MagicMock(); empty_cursor.fetchall.return_value = []
        mock_conn.execute.side_effect = [comment_cursor, empty_cursor, empty_cursor]

        with patch("app.core.tickets_service.db.get_conn", return_value=mock_conn):
            timeline = tickets_service.get_timeline(ticket_id=123, limit=10, include_emails=False)

        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["event_type"], "transicion")
        self.assertIn("asignado -> en_progreso", timeline[0]["detail"])
        self.assertEqual(timeline[1]["event_type"], "comment")
        self.assertEqual(timeline[1]["detail"], "Cliente aporta más contexto")

        for item in timeline:
            self.assertTrue(item.get("created_at"), f"Evento sin created_at: {item}")
            self._assert_iso8601(item["created_at"])

        # El agregador debe respetar orden descendente por fecha (tal como llega de la query SQL).
        created = [item["created_at"] for item in timeline]
        self.assertEqual(created, sorted(created, reverse=True))
        queries = [call.args[0] for call in mock_conn.execute.call_args_list]
        joined = "\n\n".join(queries)
        self.assertIn("ORDER BY", joined)
        self.assertIn("DESC", joined)
        self.assertIn("LIMIT ?", joined)
        mock_conn.close.assert_called_once()


class TicketEmailNotificationTests(unittest.TestCase):
    def test_notify_client_assignment_uses_reply_subject_and_thread_headers(self) -> None:
        ticket = {
            "id": 101,
            "codigo": "TK-20-03-2026-0001",
            "titulo": "Falla correo",
            "origen_email": "cliente@example.com",
            "email_thread_id": "<parent@example.com>",
            "email_references": "<older@example.com>",
        }
        conn = MagicMock()

        with (
            patch("app.core.tickets_service.get_ticket", return_value=ticket),
            patch("app.core.tickets_service.db.get_conn", return_value=conn),
            patch("app.core.tickets_service.db.now_utc_iso", return_value="2026-03-20T12:00:00+00:00"),
            patch(
                "app.core.tickets_service.email_sender.send_email_advanced",
                return_value={"from_addr": "soporte@example.com", "message_id": "<msg-assignment@example.com>"},
            ) as send_email,
            patch("app.core.tickets_service._update_ticket_thread_metadata") as update_thread,
        ):
            tickets_service.notify_client_assignment(ticket, "Especialista Uno")

        kwargs = send_email.call_args.kwargs
        self.assertEqual(kwargs["subject"], "Re: [TK-20-03-2026-0001] Falla correo")
        self.assertEqual(kwargs["to_email"], "cliente@example.com")
        self.assertEqual(
            kwargs["headers"],
            {"In-Reply-To": "<parent@example.com>", "References": "<older@example.com> <parent@example.com>"},
        )

        update_thread.assert_called_once_with(
            conn,
            101,
            message_id="<msg-assignment@example.com>",
            in_reply_to="<parent@example.com>",
            references="<older@example.com> <parent@example.com>",
        )
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_notify_client_resolution_uses_configured_auto_close_window(self) -> None:
        ticket = {
            "id": 102,
            "codigo": "TK-20-03-2026-0002",
            "titulo": "Incidente mayor",
            "origen_email": "cliente@example.com",
            "email_thread_id": "<thread@example.com>",
            "email_references": "<history@example.com>",
        }
        conn = MagicMock()

        with (
            patch("app.core.tickets_service.get_ticket", return_value=ticket),
            patch("app.core.tickets_service._get_auto_close_hours", return_value=36),
            patch("app.core.tickets_service.db.get_conn", return_value=conn),
            patch("app.core.tickets_service.db.now_utc_iso", return_value="2026-03-20T12:00:00+00:00"),
            patch(
                "app.core.tickets_service.email_sender.send_email_advanced",
                return_value={"from_addr": "soporte@example.com", "message_id": "<msg-resolution@example.com>"},
            ) as send_email,
            patch("app.core.tickets_service._update_ticket_thread_metadata") as update_thread,
        ):
            tickets_service.notify_client_resolution(ticket)

        kwargs = send_email.call_args.kwargs
        self.assertEqual(kwargs["subject"], "Re: [TK-20-03-2026-0002] Incidente mayor")
        self.assertIn("36 horas", kwargs["html_body"])
        self.assertEqual(kwargs["to_email"], "cliente@example.com")
        self.assertEqual(
            kwargs["headers"],
            {"In-Reply-To": "<thread@example.com>", "References": "<history@example.com> <thread@example.com>"},
        )

        update_thread.assert_called_once_with(
            conn,
            102,
            message_id="<msg-resolution@example.com>",
            in_reply_to="<thread@example.com>",
            references="<history@example.com> <thread@example.com>",
        )
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_get_auto_close_hours_reads_db_setting(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"value": "48"}

        with patch("app.core.tickets_service.db.get_conn", return_value=conn):
            hours = tickets_service._get_auto_close_hours()

        self.assertEqual(hours, 48)
        conn.close.assert_called_once()


class EmailIntegrationParsingTests(unittest.TestCase):
    def test_parse_email_decodes_subject_body_and_attachment(self) -> None:
        msg = MIMEMultipart()
        msg["Subject"] = Header("Prueba ñ", "utf-8").encode()
        msg["From"] = "Cliente E2E <cliente@example.com>"
        msg["Message-ID"] = "<imap@example.com>"
        msg.attach(MIMEText("Linea 1\nLinea 2", "plain", "utf-8"))
        msg.attach(MIMEText("<p>Linea <strong>HTML</strong></p>", "html", "utf-8"))

        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"hola mundo")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=Header("adjunto-á.txt", "utf-8").encode(),
        )
        msg.attach(attachment)

        processor = email_integration.EmailProcessor.__new__(email_integration.EmailProcessor)
        with patch("builtins.print"):
            parsed = processor.parse_email(msg)

        self.assertEqual(parsed["subject"], "Prueba ñ")
        self.assertEqual(parsed["sender"], "Cliente E2E <cliente@example.com>")
        self.assertEqual(parsed["message_id"], "<imap@example.com>")
        self.assertIn("Linea 1", parsed["body"])
        self.assertEqual(len(parsed["attachments"]), 1)
        self.assertEqual(parsed["attachments"][0]["filename"], "adjunto-á.txt")
        self.assertEqual(base64.b64decode(parsed["attachments"][0]["data_base64"]), b"hola mundo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
