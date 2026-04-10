from __future__ import annotations

from typing import Any, Dict, List, Optional

# Roles con ejecución técnica real (pueden operar ticket cuando corresponde).
ROLES_TECNICOS: tuple[str, ...] = ("redes", "sistemas", "implementaciones", "ops")
ROLES_TECNICOS_SET = set(ROLES_TECNICOS)

# Roles de gestión global.
ROLES_ADMIN_GESTION = {"admin", "encargado_mesa"}
ROLES_DESPACHO_MESA = {"ops", "encargado_mesa"}


def normalize_roles(value: Optional[Any]) -> List[str]:
    out: List[str] = []
    if value is None:
        return out

    if isinstance(value, (list, tuple, set)):
        for item in value:
            role = str(item or "").strip().lower()
            if role and role not in out:
                out.append(role)
        return out

    raw = str(value or "").strip().lower()
    if not raw:
        return out
    if "," in raw:
        for token in raw.split(","):
            role = token.strip().lower()
            if role and role not in out:
                out.append(role)
        return out
    return [raw]


def normalize_role(value: Optional[Any]) -> str:
    roles = normalize_roles(value)
    return roles[0] if roles else ""


def normalize_username(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def scope_enforced(actor_role: Optional[Any]) -> bool:
    return bool(normalize_roles(actor_role))


def is_admin_management_role(actor_role: Optional[Any]) -> bool:
    return any(role in ROLES_ADMIN_GESTION for role in normalize_roles(actor_role))


def is_tech_execution_role(actor_role: Optional[Any]) -> bool:
    return any(role in ROLES_TECNICOS_SET for role in normalize_roles(actor_role))


def is_dispatcher_role(actor_role: Optional[Any]) -> bool:
    return any(role in ROLES_DESPACHO_MESA for role in normalize_roles(actor_role))


def ticket_assignee_username(ticket: Dict[str, Any]) -> str:
    return normalize_username(ticket.get("asignado_a"))


def can_dispatch_reassign(
    ticket: Dict[str, Any],
    actor_id: str,
    actor_role: Optional[Any],
) -> bool:
    if is_admin_management_role(actor_role):
        return True
    if not is_dispatcher_role(actor_role):
        return False
    actor = normalize_username(actor_id)
    assignee = ticket_assignee_username(ticket)
    return (not assignee) or (assignee == actor)


def can_manage(ticket: Dict[str, Any], actor_id: str, actor_role: Optional[Any]) -> bool:
    if not scope_enforced(actor_role):
        return True
    if is_admin_management_role(actor_role):
        return True

    actor = normalize_username(actor_id)
    assignee = ticket_assignee_username(ticket)
    return bool(assignee and assignee == actor)


def can_participate(ticket: Dict[str, Any], actor_id: str, actor_role: Optional[Any]) -> bool:
    if not scope_enforced(actor_role):
        return True

    has_admin = is_admin_management_role(actor_role)
    has_tech = is_tech_execution_role(actor_role)
    if has_admin and not has_tech:
        return False

    if has_admin and has_tech:
        actor = normalize_username(actor_id)
        assignee = ticket_assignee_username(ticket)
        return bool(assignee and assignee == actor)

    return can_manage(ticket, actor_id, actor_role)


def require_can_manage(
    ticket: Dict[str, Any],
    actor_id: str,
    actor_role: Optional[Any],
    action_label: str,
) -> None:
    if not scope_enforced(actor_role):
        return
    if is_admin_management_role(actor_role):
        return

    actor = normalize_username(actor_id)
    assignee = ticket_assignee_username(ticket)
    if assignee and assignee != actor:
        raise PermissionError(
            f"Ticket asignado a '{ticket.get('asignado_a')}'. Solo el asignado puede {action_label}."
        )
    if not assignee:
        raise PermissionError(
            f"Ticket sin asignar. Primero debes tomar el ticket para {action_label}."
        )


def require_can_participate(
    ticket: Dict[str, Any],
    actor_id: str,
    actor_role: Optional[Any],
    action_label: str,
) -> None:
    if not scope_enforced(actor_role):
        return

    has_admin = is_admin_management_role(actor_role)
    has_tech = is_tech_execution_role(actor_role)
    if has_admin and not has_tech:
        raise PermissionError(
            "El admin no puede intervenir en correo/comentarios/adjuntos. "
            "Solo puede gestionar estado o asignación."
        )

    if has_admin and has_tech:
        actor = normalize_username(actor_id)
        assignee = ticket_assignee_username(ticket)
        if assignee and assignee != actor:
            raise PermissionError(
                f"Ticket asignado a '{ticket.get('asignado_a')}'. Solo el asignado puede {action_label}."
            )
        if not assignee:
            raise PermissionError(
                f"Ticket sin asignar. Primero debes tomar el ticket para {action_label}."
            )
        return

    require_can_manage(ticket, actor_id, actor_role, action_label)

