from typing import Optional, Any, Dict, List
from fastapi import HTTPException, Header, Cookie
from app.core import security
from app.core.config import settings

def _bearer_token(auth: Optional[str]) -> str:
    if not auth: return ""
    parts = auth.split(" ", 1)
    return parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else ""

def require_session(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="missing_auth")
    
    payload = security.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid_token")
        
    return {
        "username": payload["sub"],
        "role": payload["role"]
    }

def require_session_hybrid(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None)
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

    return {
        "username": payload["sub"],
        "role": payload["role"]
    }

def require_permission(permission: str):
    """
    Middleware RBAC: Verifica si el rol del usuario tiene el permiso requerido.
    Usa la matriz definida en core.config.settings.
    """
    def dep(
        authorization: Optional[str] = Header(default=None),
        access_token: Optional[str] = Cookie(default=None)
    ):
        sess = require_session_hybrid(authorization, access_token)
        role = sess["role"]
        
        allowed_perms = settings.ROLE_PERMISSIONS.get(role, [])
        
        if "*" in allowed_perms:
            return sess
            
        if permission not in allowed_perms:
            raise HTTPException(
                status_code=403, 
                detail=f"RBAC: Rol '{role}' no tiene permiso '{permission}'"
            )
            
        return sess
    return dep

# Legacy helper fallback (optional)
def require_roles(sess: Dict[str, Any], allowed: List[str]) -> None:
    if sess.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="forbidden")
