from typing import Optional, List, Any, Dict
from fastapi import HTTPException, Header
import nucleo as db

def _bearer_token(auth: Optional[str]) -> str:
    if not auth:
        return ""
    parts = auth.split(" ", 1)
    if len(parts) != 2:
        return ""
    if parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()

def require_session(authorization: Optional[str]) -> Dict[str, Any]:
    token = _bearer_token(authorization)
    sess = db.get_session(token)
    if not sess:
        raise HTTPException(status_code=401, detail="invalid_session")
    return sess

def require_roles(sess: Dict[str, Any], allowed: List[str]) -> None:
    if sess.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="forbidden")
