from typing import Optional, Dict, Any, List
from plataforma.core import db, security, organigrama
from plataforma.core.config import settings
import unicodedata
import json
import re


ALLOWED_ROLES = set(settings.ROLE_PERMISSIONS.keys())

def get_user_display_name(username: str) -> str:
    """Nombre real del usuario = '{first_name} {last_name}'.trim().

    Vacío si no está cargado: el consumidor (sidebar, ticketera, etc.) aplica su
    propio fallback (derivar del correo). La identidad central es la única fuente.
    """
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT first_name, last_name FROM users WHERE username = ?",
            (str(username or "").strip(),),
        ).fetchone()
        if not row:
            return ""
        return f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
    finally:
        conn.close()


def get_users_display_names(usernames: List[str]) -> Dict[str, str]:
    """Mapa {username: display_name} en LOTE. Para endpoints que listan varios usuarios
    (comentarios, transiciones, líderes de área) sin una query por cada uno. Devuelve nombre
    vacío si el usuario no tiene first/last cargado (el caller aplica su fallback)."""
    clean = sorted({str(u or "").strip() for u in (usernames or []) if str(u or "").strip()})
    if not clean:
        return {}
    conn = db.get_conn()
    try:
        placeholders = ",".join("?" for _ in clean)
        rows = conn.execute(
            f"SELECT username, first_name, last_name FROM users WHERE username IN ({placeholders})",
            tuple(clean),
        ).fetchall()
        out: Dict[str, str] = {}
        for r in rows:
            u = str(r.get("username") or "").strip()
            if u:
                out[u] = f"{(r.get('first_name') or '').strip()} {(r.get('last_name') or '').strip()}".strip()
        return out
    finally:
        conn.close()


def _normalize_role(raw_role: str) -> str:
    role = unicodedata.normalize("NFKD", str(raw_role or ""))
    role = role.encode("ascii", "ignore").decode("ascii")
    role = role.strip().lower().replace("-", "_").replace(" ", "_")
    if "encargado" in role and "mesa" in role:
        return "encargado_mesa"
    aliases = {
        "encargado_de_mesa_de_ayuda": "encargado_mesa",
        "encargado_mesa_de_ayuda": "encargado_mesa",
        "encargado_mesa_ayuda": "encargado_mesa",
        "encargado_de_mesa_ayuda": "encargado_mesa",
        "encargado_de_mesa": "encargado_mesa",
        "encargado_mesa": "encargado_mesa",
        "mesa_de_ayuda": "encargado_mesa",
        "operaciones": "pmo",
    }
    # Renombres legacy (warehouse→bodega, finance→finanzas, ops/implementaciones→pmo): fuente
    # única en organigrama.canonizar_rol, no duplicados acá.
    return organigrama.canonizar_rol(aliases.get(role, role))


def _normalize_secondary_roles(raw_roles: Any, primary_role: str) -> List[str]:
    parsed: List[str] = []
    source = raw_roles

    if source is None:
        return parsed

    if isinstance(source, str):
        text = source.strip()
        if not text:
            return parsed
        try:
            source = json.loads(text)
        except Exception:
            source = [token.strip() for token in text.split(",") if token.strip()]

    if not isinstance(source, (list, tuple, set)):
        return parsed

    primary_norm = _normalize_role(primary_role)
    for item in source:
        normalized = _normalize_role(str(item or "").strip())
        if not normalized:
            continue
        if normalized not in ALLOWED_ROLES:
            continue
        if normalized == primary_norm:
            continue
        if normalized in parsed:
            continue
        parsed.append(normalized)
    return parsed

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT username, password_hash, role, secondary_roles, is_active FROM users WHERE username=?",
            (username.strip(),)
        ).fetchone()
        
        if not row or int(row["is_active"] or 0) != 1:
            return None
            
        if not security.verify_password(password, row["password_hash"]):
            return None
            
        role = _normalize_role(row["role"])
        secondary_roles = _normalize_secondary_roles(row.get("secondary_roles"), role)
        roles = [role] + [r for r in secondary_roles if r != role]
        return {
            "username": row["username"],
            "role": role,
            "roles": roles,
            "secondary_roles": secondary_roles,
        }
    finally:
        conn.close()

def create_user(username: str, password: str, role: str, secondary_roles: Optional[List[str]] = None) -> None:
    # Validacion basica
    username = username.strip()
    role = _normalize_role(role)
    if role not in ALLOWED_ROLES:
        raise ValueError("Role invalido")
    normalized_secondary = _normalize_secondary_roles(secondary_roles or [], role)

    hashed_pw = security.get_password_hash(password)
    
    conn = db.get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            # Silent fail or raise? Raise allows API to handle 409
            raise RuntimeError("Usuario ya existe")
            
        conn.execute(
            "INSERT INTO users (username, password_hash, role, secondary_roles, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (username, hashed_pw, role, json.dumps(normalized_secondary), db.now_utc_iso())
        )
        conn.commit()
    finally:
        conn.close()

def get_effective_allowed_modules(username: str, roles: List[str]) -> List[str]:
    """
    Calcula la lista de módulos de UI permitidos para un usuario.
    Centralizado para Gateway y microservicios.
    """
    conn = db.get_conn()
    try:
        # 1. Intentar obtener el override explícito
        row = conn.execute(
            "SELECT allowed_modules FROM users WHERE username = ?", (username,)
        ).fetchone()

        if row and row.get("allowed_modules"):
            try:
                parsed = json.loads(row["allowed_modules"])
                if isinstance(parsed, list) and parsed:
                    return parsed
            except Exception:
                pass

        # 2. Derivar desde roles
        all_user_roles = sorted(list(set(roles or [])))
        
        if "admin" in all_user_roles:
            return [module["id"] for module in settings.UI_MODULES]

        effective_modules = set()
        all_permissions = set()

        for role in all_user_roles:
            permissions_for_role = settings.ROLE_PERMISSIONS.get(role, [])
            all_permissions.update(permissions_for_role)
        
        if "*" in all_permissions:
            return [module["id"] for module in settings.UI_MODULES]

        for perm in all_permissions:
            key = perm.split(":")[0] if ":" in perm else perm
            module_id = settings.PERMISSION_TO_MODULE_MAP.get(key)
            if module_id:
                effective_modules.add(module_id)

        # Ordenar por el orden definido en config
        module_order = {module["id"]: i for i, module in enumerate(settings.UI_MODULES)}
        return sorted(list(effective_modules), key=lambda m: module_order.get(m, 999))

    finally:
        conn.close()
