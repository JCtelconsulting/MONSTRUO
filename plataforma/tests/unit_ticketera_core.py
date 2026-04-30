#!/usr/bin/env python3
from __future__ import annotations

import base64
import asyncio
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
PROJECT_ROOT = THIS_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ticketera.backend.services import roles as ticket_roles
from ticketera.backend.services import workflow as ticket_workflow
from plataforma.core import email_integration
from plataforma.core import jobs_engine
from ticketera.backend.services import service as tickets_service


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

        with patch("ticketera.backend.services.service.db.get_conn", return_value=mock_conn):
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
            patch("ticketera.backend.services.service.get_ticket", return_value=ticket),
            patch("ticketera.backend.services.service.db.get_conn", return_value=conn),
            patch("ticketera.backend.services.service.db.now_utc_iso", return_value="2026-03-20T12:00:00+00:00"),
            patch(
                "ticketera.backend.services.service.email_sender.send_email_advanced",
                return_value={"from_addr": "soporte@example.com", "message_id": "<msg-assignment@example.com>"},
            ) as send_email,
            patch("ticketera.backend.services.service._update_ticket_thread_metadata") as update_thread,
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
            patch("ticketera.backend.services.service.get_ticket", return_value=ticket),
            patch("ticketera.backend.services.service._get_auto_close_hours", return_value=36),
            patch("ticketera.backend.services.service.db.get_conn", return_value=conn),
            patch("ticketera.backend.services.service.db.now_utc_iso", return_value="2026-03-20T12:00:00+00:00"),
            patch(
                "ticketera.backend.services.service.email_sender.send_email_advanced",
                return_value={"from_addr": "soporte@example.com", "message_id": "<msg-resolution@example.com>"},
            ) as send_email,
            patch("ticketera.backend.services.service._update_ticket_thread_metadata") as update_thread,
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

        with patch("ticketera.backend.services.service.db.get_conn", return_value=conn):
            hours = tickets_service._get_auto_close_hours()

        self.assertEqual(hours, 48)
        conn.close.assert_called_once()


class TicketeraEpic11Tests(unittest.TestCase):
    def test_list_ticketera_mail_templates_returns_four_effective_templates(self) -> None:
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        conn.execute.return_value = cursor

        with patch("ticketera.backend.services.service.db.get_conn", return_value=conn):
            templates = tickets_service.list_ticketera_mail_templates()

        self.assertEqual(len(templates), 4)
        self.assertEqual(
            [item["key"] for item in templates],
            [
                tickets_service.MAIL_TEMPLATE_KEY_AUTO_REPLY,
                tickets_service.MAIL_TEMPLATE_KEY_CLIENT_ASSIGNMENT,
                tickets_service.MAIL_TEMPLATE_KEY_SPECIALIST_ASSIGNMENT,
                tickets_service.MAIL_TEMPLATE_KEY_RESOLUTION,
            ],
        )
        self.assertTrue(all(item["subject_template"] for item in templates))
        self.assertTrue(all(item["body_template"] for item in templates))

    def test_resolve_routing_category_prioritizes_exact_email(self) -> None:
        conn = MagicMock()
        email_cursor = MagicMock()
        email_cursor.fetchone.return_value = {"categoria": "redes"}
        conn.execute.return_value = email_cursor

        categoria = tickets_service._resolve_routing_category_for_email(conn, "Cliente <cliente@empresa.cl>")

        self.assertEqual(categoria, "redes")
        self.assertEqual(conn.execute.call_count, 1)

    def test_resolve_routing_category_uses_domain_when_exact_email_is_missing(self) -> None:
        conn = MagicMock()
        email_cursor = MagicMock()
        email_cursor.fetchone.return_value = None
        domain_cursor = MagicMock()
        domain_cursor.fetchone.return_value = {"categoria": "sistemas"}
        conn.execute.side_effect = [email_cursor, domain_cursor]

        categoria = tickets_service._resolve_routing_category_for_email(conn, "cliente@empresa.cl")

        self.assertEqual(categoria, "sistemas")
        self.assertEqual(conn.execute.call_count, 2)

    def test_create_ticket_falls_back_to_classifier_when_routing_has_no_match(self) -> None:
        conn = MagicMock()

        def _execute(sql: str, params=None):
            cursor = MagicMock()
            lowered = " ".join(str(sql).lower().split())
            if "insert into tickets" in lowered:
                cursor.fetchone.return_value = {"id": 55}
                return cursor
            if "update tickets set codigo" in lowered:
                return cursor
            if "insert into ticket_transitions" in lowered:
                return cursor
            return cursor

        conn.execute.side_effect = _execute

        with (
            patch("ticketera.backend.services.service.db.get_conn", return_value=conn),
            patch("ticketera.backend.services.service.db.now_utc_iso", return_value="2026-03-23T12:00:00+00:00"),
            patch("ticketera.backend.services.service.get_client_for_email", return_value=None),
            patch("ticketera.backend.services.service._resolve_routing_category_for_email", return_value=None) as resolve_route,
            patch("ticketera.backend.services.service.clasificar_ticket", return_value="general") as classify_ticket,
            patch("ticketera.backend.services.service._find_customer_by_email", return_value=None),
            patch("ticketera.backend.services.service._evaluate_ticket_sla"),
            patch("ticketera.backend.services.service.get_ticket", return_value={"id": 55, "categoria": "general"}),
        ):
            ticket = tickets_service.create_ticket(
                titulo="Incidente sin regla",
                descripcion="Debe usar clasificación automática",
                creador_id="tester",
                categoria=None,
                origen_email="cliente@empresa.cl",
            )

        self.assertEqual(ticket["categoria"], "general")
        resolve_route.assert_called_once()
        classify_ticket.assert_called_once_with("Incidente sin regla", "Debe usar clasificación automática")

    def test_auto_reply_templates_render_from_db_and_fallback_to_default(self) -> None:
        ticket = {
            "id": 42,
            "codigo": "TK-23-03-2026-0042",
            "titulo": "Router caído",
            "cliente_nombre": "Cliente Demo",
            "asignado_a": "tecnico1",
        }

        configured_conn = MagicMock()
        configured_subject = MagicMock()
        configured_subject.fetchone.return_value = {"value": "Acuse {{ticket_code}} para {{customer_name}}"}
        configured_body = MagicMock()
        configured_body.fetchone.return_value = {"value": "Hola {{customer_name}}, revisaremos {{ticket_title}} con {{assignee_name}}."}
        configured_conn.execute.side_effect = [configured_subject, configured_body]

        subject = tickets_service._auto_reply_subject(configured_conn, ticket, nombre="Cliente Demo", asignado_a="Técnico Uno")
        body = tickets_service._auto_reply_body(configured_conn, ticket, "Cliente Demo", "Técnico Uno")

        self.assertEqual(subject, "Acuse TK-23-03-2026-0042 para Cliente Demo")
        self.assertIn("Hola Cliente Demo", body)
        self.assertIn("Router caído", body)
        self.assertIn("Técnico Uno", body)

        fallback_conn = MagicMock()
        empty_subject = MagicMock()
        empty_subject.fetchone.return_value = None
        empty_body = MagicMock()
        empty_body.fetchone.return_value = None
        fallback_conn.execute.side_effect = [empty_subject, empty_body]

        fallback_subject = tickets_service._auto_reply_subject(fallback_conn, ticket, nombre="Cliente Demo", asignado_a="Mesa")
        fallback_body = tickets_service._auto_reply_body(fallback_conn, ticket, "Cliente Demo", "Mesa")

        self.assertEqual(fallback_subject, "Re: [TK-23-03-2026-0042] Router caído")
        self.assertIn("Hemos recibido su solicitud", fallback_body)
        self.assertIn("TK-23-03-2026-0042", fallback_body)

    def test_notify_specialist_assignment_uses_configured_template(self) -> None:
        ticket = {
            "id": 88,
            "codigo": "TK-23-03-2026-0088",
            "titulo": "VPN intermitente",
        }
        conn = MagicMock()
        subject_cursor = MagicMock()
        subject_cursor.fetchone.return_value = {"value": "Nueva tarea {{ticket_code}}"}
        body_cursor = MagicMock()
        body_cursor.fetchone.return_value = {"value": "Hola, revisa {{ticket_title}}."}
        conn.execute.side_effect = [subject_cursor, body_cursor]

        with (
            patch("ticketera.backend.services.service.db.get_conn", return_value=conn),
            patch("ticketera.backend.services.service.email_sender.send_email_advanced") as send_email,
        ):
            tickets_service.notify_specialist_assignment("tecnico@example.com", ticket)

        kwargs = send_email.call_args.kwargs
        self.assertEqual(kwargs["subject"], "Nueva tarea TK-23-03-2026-0088")
        self.assertIn("revisa VPN intermitente", kwargs["html_body"])
        self.assertEqual(kwargs["to_email"], "tecnico@example.com")

    def test_status_update_notify_sends_internal_email(self) -> None:
        ticket = {
            "id": 89,
            "codigo": "TK-23-03-2026-0089",
            "titulo": "Firewall caido",
            "notify_emails": "dueno@example.com, supervisor@example.com",
            "email_thread_id": "<status-parent@example.com>",
            "email_references": "<status-history@example.com>",
        }
        conn = MagicMock()

        with (
            patch("ticketera.backend.services.service.db.get_conn", return_value=conn),
            patch("ticketera.backend.services.service.db.now_utc_iso", return_value="2026-03-26T16:00:00+00:00"),
            patch(
                "ticketera.backend.services.service.email_sender.send_email_advanced",
                return_value={"from_addr": "soporte@example.com", "message_id": "<msg-status@example.com>"},
            ) as send_email,
            patch("ticketera.backend.services.service._update_ticket_thread_metadata") as update_thread,
        ):
            result = tickets_service._send_ticket_status_update_to_notify_emails(
                ticket,
                from_estado="abierto",
                to_estado="en_progreso",
                actor_id="encargado.mesa",
                motivo="Escalado a mesa interna",
            )

        self.assertTrue(result["sent"])
        kwargs = send_email.call_args.kwargs
        self.assertEqual(kwargs["to_email"], "dueno@example.com")
        self.assertEqual(kwargs["cc_emails"], ["supervisor@example.com"])
        self.assertEqual(kwargs["subject"], "Re: [TK-23-03-2026-0089] Firewall caido")
        self.assertIn("Abierto -> En progreso", kwargs["html_body"])
        self.assertIn("Escalado a mesa interna", kwargs["html_body"])
        self.assertIn("encargado.mesa", kwargs["html_body"])
        update_thread.assert_called_once_with(
            conn,
            89,
            message_id="<msg-status@example.com>",
            in_reply_to="<status-parent@example.com>",
            references="<status-history@example.com> <status-parent@example.com>",
        )
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_send_auto_response_job_uses_template_helpers_with_connection(self) -> None:
        ticket = {
            "id": 91,
            "codigo": "TK-23-03-2026-0091",
            "titulo": "Correo entrante",
            "cliente_nombre": "Cliente Demo",
            "email_thread_id": "<parent@example.com>",
            "email_references": "<history@example.com>",
        }
        conn = MagicMock()
        lock_cursor = MagicMock()
        lock_cursor.fetchone.return_value = {"locked": True}
        sent_cursor = MagicMock()
        sent_cursor.fetchone.return_value = None
        pending_cursor = MagicMock()
        pending_cursor.fetchone.return_value = {"id": 991}
        conn.execute.side_effect = [lock_cursor, sent_cursor, pending_cursor, MagicMock(), MagicMock()]

        payload = {
            "ticket_id": 91,
            "email": "cliente@example.com",
            "nombre": "Cliente Demo",
            "asignado_a": "mesa",
            "idempotency_key": "auto_reply:91:test",
            "in_reply_to": "<parent@example.com>",
            "references": "<history@example.com>",
        }

        with (
            patch("plataforma.core.jobs_engine.db.get_conn", return_value=conn),
            patch("plataforma.core.jobs_engine.db.now_utc_iso", return_value="2026-03-26T18:30:00+00:00"),
            patch("ticketera.backend.services.service.get_ticket", return_value=ticket),
            patch("ticketera.backend.services.service._auto_reply_sender_allowed", return_value=(True, "allowed")),
            patch("ticketera.backend.services.service._auto_reply_subject", return_value="Asunto auto") as reply_subject,
            patch("ticketera.backend.services.service._auto_reply_body", return_value="<p>Cuerpo auto</p>") as reply_body,
            patch(
                "plataforma.core.email.send_email_advanced",
                return_value={"from_addr": "soporte@example.com", "message_id": "<auto-msg@example.com>"},
            ) as send_email,
            patch("ticketera.backend.services.service._emit_system_comment"),
            patch("ticketera.backend.services.service._update_ticket_thread_metadata"),
        ):
            asyncio.run(jobs_engine.send_auto_response_job(payload))

        reply_subject.assert_called_once_with(conn, ticket, "Cliente Demo", "mesa")
        reply_body.assert_called_once_with(conn, ticket, "Cliente Demo", "mesa")
        self.assertEqual(send_email.call_args.kwargs["subject"], "Asunto auto")
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_reply_is_allowed_while_ticket_is_active(self) -> None:
        for estado in ("resuelto", "cerrado"):
            with self.subTest(estado=estado):
                with self.assertRaises(ValueError):
                    tickets_service._ensure_reply_allowed_estado({"estado": estado}, "responder correos")

        tickets_service._ensure_reply_allowed_estado({"estado": "abierto"}, "responder correos")
        tickets_service._ensure_reply_allowed_estado({"estado": "en_progreso"}, "responder correos")

    def test_main_status_transition_rejects_non_adjacent_change(self) -> None:
        with self.assertRaises(tickets_service.ConflictError):
            tickets_service._validate_main_status_transition("abierto", "cerrado")

    def test_send_ticket_reply_email_uses_canonical_subject_without_legacy_signature_and_persists_attachments(self) -> None:
        ticket = {
            "id": 77,
            "codigo": "TK-23-03-2026-0077",
            "titulo": "Incidente saliente",
            "email_thread_id": "<padre@example.com>",
            "email_references": "<historial@example.com>",
        }
        stored_attachment = {
            "filename": "salida.txt",
            "path": "/tmp/salida.txt",
            "size": 14,
            "content_type": "text/plain",
            "sha256": "abc123",
        }
        email_attachment = {
            "filename": "salida.txt",
            "data": b"hola adjunto",
            "content_type": "text/plain",
        }

        lock_conn = MagicMock()
        conn = MagicMock()

        def lock_execute(sql: str, params=None):
            cursor = MagicMock()
            lowered = " ".join(str(sql).lower().split())
            if "idempotency_key" in lowered and "from ticket_emails" in lowered:
                cursor.fetchone.return_value = None
                return cursor
            if "body_html" in lowered and "from ticket_emails" in lowered:
                cursor.fetchone.return_value = None
                return cursor
            if "insert into ticket_emails" in lowered and "outgoing_pending" in lowered:
                cursor.fetchone.return_value = {"id": 990}
                return cursor
            cursor.fetchone.return_value = None
            return cursor

        lock_conn.execute.side_effect = lock_execute

        def main_execute(sql: str, params=None):
            cursor = MagicMock()
            cursor.fetchone.return_value = None
            return cursor

        conn.execute.side_effect = main_execute

        with (
            patch("ticketera.backend.services.service.db.get_conn", side_effect=[lock_conn, conn]),
            patch("ticketera.backend.services.service.db.now_utc_iso", return_value="2026-03-23T15:00:00+00:00"),
            patch(
                "ticketera.backend.services.service.email_sender.send_email_advanced",
                return_value={"from_addr": "soporte@example.com", "message_id": "<reply@example.com>"},
            ) as send_email,
            patch("ticketera.backend.services.service._maybe_mark_first_response"),
            patch("ticketera.backend.services.service._update_ticket_thread_metadata"),
            patch("ticketera.backend.services.service._evaluate_ticket_sla"),
            patch("ticketera.backend.services.service.create_evidence_event"),
        ):
            result = tickets_service._send_ticket_reply_email(
                ticket=ticket,
                author_id="tecnico1",
                clean_msg="Respuesta limpia al cliente",
                to_email="cliente@example.com",
                cc_emails=["cc@example.com"],
                bcc_emails=["cco@example.com"],
                to_addr_record="cliente@example.com",
                email_attachments=[email_attachment],
                stored_attachments=[stored_attachment],
                idempotency_key="reply-test-1",
            )

        send_kwargs = send_email.call_args.kwargs
        self.assertEqual(send_kwargs["subject"], "Re: [TK-23-03-2026-0077] Incidente saliente")
        self.assertEqual(send_kwargs["attachments"][0]["filename"], "salida.txt")
        self.assertNotIn("Mesa de Ayuda", send_kwargs["html_body"])
        self.assertEqual(result["sent_email_id"], 990)

        executed_sql = "\n".join(str(call.args[0]) for call in conn.execute.call_args_list)
        self.assertIn("INSERT INTO ticket_attachments", executed_sql)
        self.assertIn("INSERT INTO ticket_comments", executed_sql)


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
