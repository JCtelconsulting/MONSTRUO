#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
CODE_ROOT = PROJECT_ROOT / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from app.core.tickets import roles as ticket_roles
from app.core.tickets import workflow as ticket_workflow
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

        self.assertEqual(len(timeline), 3)
        self.assertEqual(timeline[0]["evento"], "Transicion")
        self.assertIn("asignado -> en_progreso", timeline[0]["detalle"])
        self.assertEqual(timeline[1]["evento"], "Nota")
        self.assertEqual(timeline[1]["detalle"], "Cliente aporta más contexto")

        for item in timeline:
            self.assertTrue(item.get("created_at"), f"Evento sin created_at: {item}")
            self._assert_iso8601(item["created_at"])

        # El agregador debe respetar orden descendente por fecha (tal como llega de la query SQL).
        created = [item["created_at"] for item in timeline]
        self.assertEqual(created, sorted(created, reverse=True))

        sql = mock_conn.execute.call_args.args[0]
        self.assertIn("ORDER BY created_at DESC", sql)
        self.assertIn("LIMIT ?", sql)
        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)

