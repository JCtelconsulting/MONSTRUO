from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import Cookie, Header, HTTPException

from plataforma.core import security
from plataforma.core.config import settings

logger = logging.getLogger(__name__)


def _bearer_token(auth: Optional[str]) -> str:
    if not auth:
        return ""
    parts = auth.split(" ", 1)
    return parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else ""


def _payload_roles(payload: Dict[str, Any]) -> List[str]:
    primary = str(payload.get("role") or "").strip().lower()
    raw_roles = payload.get("roles")
    out: List[str] = []
    if isinstance(raw_roles, list):
        for item in raw_roles:
            role = str(item or "").strip().lower()
            if role and role not in out:
                out.append(role)
    if primary and primary not in out:
        out.insert(0, primary)
    return out or ([primary] if primary else [])


def _get_role_permissions(role: str) -> List[str]:
    """Read permissions for a role from DB, falling back to config.py."""
    try:
        from plataforma.core import db
        conn = db.get_conn()
        try:
            rows = conn.execute(
                "SELECT permission FROM core.sys_role_permissions WHERE role = %s",
                (role,),
            ).fetchall()
            if rows:
                return [str(r["permission"]) for r in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.debug("DB role lookup failed for %s, using config fallback: %s", role, e)
    return list(settings.ROLE_PERMISSIONS.get(role, []))


def require_session(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="missing_auth")
    payload = security.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid_token")
    roles = _payload_roles(payload)
    role = roles[0] if roles else ""
    return {"username": payload["sub"], "role": role, "roles": roles}


def require_session_hybrid(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
) -> Dict[str, Any]:
    token = _bearer_token(authorization)
    if not token and access_token:
        if access_token.startswith("Bearer ") or access_token.startswith("bearer "):
            token = access_token[7:].strip()
        else:
            token = access_token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing_auth")
    payload = security.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid_token")
    roles = _payload_roles(payload)
    role = roles[0] if roles else ""
    return {"username": payload["sub"], "role": role, "roles": roles}


def require_permission(permission: str):
    """RBAC: checks if any of the user's roles has the required permission.
    Reads from DB first, falls back to config.py."""
    def dep(
        authorization: Optional[str] = Header(default=None),
        access_token: Optional[str] = Cookie(default=None),
    ) -> Dict[str, Any]:
        sess = require_session_hybrid(authorization, access_token)
        roles = [str(r or "").strip().lower() for r in (sess.get("roles") or [sess.get("role")])]
        roles = [r for r in roles if r]

        allowed_perms: set[str] = set()
        for role in roles:
            perms = _get_role_permissions(role)
            if "*" in perms:
                return sess
            allowed_perms.update(perms)

        if permission in allowed_perms:
            return sess

        role_label = " + ".join(roles) if roles else "-"
        raise HTTPException(
            status_code=403,
            detail=f"RBAC: Roles '{role_label}' no tienen permiso '{permission}'",
        )

    return dep


def require_roles(sess: Dict[str, Any], allowed: List[str]) -> None:
    if sess.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="forbidden")
