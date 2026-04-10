
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from core import security

class AuthIdentityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Default: user is None or anonymous
        request.state.user = None
        
        # Intentar extraer identidad del Token (Header o Cookie)
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
        elif "access_token" in request.cookies:
            # Fallback para compatibilidad navegador
            cookie = request.cookies["access_token"]
            if cookie.startswith("Bearer "):
                token = cookie[7:]
            else:
                token = cookie
        
        if token:
            payload = security.verify_token(token)
            if payload:
                payload_roles = payload.get("roles")
                roles = []
                if isinstance(payload_roles, list):
                    for item in payload_roles:
                        role_item = str(item or "").strip().lower()
                        if role_item and role_item not in roles:
                            roles.append(role_item)
                primary_role = str(payload.get("role") or "").strip().lower()
                if primary_role and primary_role not in roles:
                    roles.insert(0, primary_role)
                # Inyectamos la identidad en el state
                # Payload suele tener: {"sub": "juan", "role": "admin", "exp": ...}
                request.state.user = {
                    "username": payload.get("sub"),
                    "role": primary_role,
                    "roles": roles,
                }
        
        response = await call_next(request)
        return response
