from datetime import datetime, timedelta, timezone
from typing import Optional, Any, List
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings

# Esquema compatible con Django y el nuevo (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt", "django_pbkdf2_sha256", "pbkdf2_sha256"], deprecated="auto")

def create_access_token(
    subject: Any,
    role: str,
    expires_delta: Optional[timedelta] = None,
    roles: Optional[List[str]] = None,
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    normalized_primary = str(role or "").strip().lower()
    normalized_roles: list[str] = []
    for item in roles or []:
        parsed = str(item or "").strip().lower()
        if parsed and parsed not in normalized_roles:
            normalized_roles.append(parsed)
    if normalized_primary and normalized_primary not in normalized_roles:
        normalized_roles.insert(0, normalized_primary)

    to_encode = {
        "sub": str(subject),
        "role": normalized_primary or role,
        "roles": normalized_roles,
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except Exception:
        return None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
