"""Servicios para CRUD de usuarios (admin)."""

from sqlalchemy.orm import Session

from backend import modelos
from backend.core import dependencias


def list_users(db: Session) -> list[modelos.User]:
    return db.query(modelos.User).order_by(modelos.User.email).all()


def create_user(
    db: Session, email: str, name: str, role, password: str
) -> modelos.User:
    """Crea un usuario nuevo. Lanza ValueError si el email ya esta en uso."""
    email_lower = email.lower()
    if db.query(modelos.User).filter(modelos.User.email == email_lower).first():
        raise ValueError("Email en uso")
    user = modelos.User(
        email=email_lower,
        name=name,
        role=role,
        hashed_password=dependencias.get_db_hash(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user_id: int,
    email: str | None = None,
    name: str | None = None,
    role=None,
) -> modelos.User:
    """Actualiza campos opcionales de un usuario.

    Lanza LookupError si no existe.
    Lanza ValueError si email es invalido o ya esta en uso.
    """
    user = db.query(modelos.User).filter(modelos.User.id == user_id).first()
    if not user:
        raise LookupError("No encontrado")

    if email is not None:
        new_email = email.strip().lower()
        if not new_email:
            raise ValueError("Email invalido")
        if new_email != (user.email or "").lower():
            if db.query(modelos.User).filter(modelos.User.email == new_email).first():
                raise ValueError("Email en uso")
            user.email = new_email

    if name is not None:
        user.name = (name or "").strip()

    if role is not None:
        user.role = role

    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int, current_user_id: int | None) -> None:
    """Borra un usuario. Lanza ValueError si intenta autoborrarse,
    LookupError si no existe."""
    if current_user_id and current_user_id == user_id:
        raise ValueError("No puedes eliminar tu propio usuario")
    user = db.query(modelos.User).filter(modelos.User.id == user_id).first()
    if not user:
        raise LookupError("No encontrado")
    db.delete(user)
    db.commit()


def reset_user_password(db: Session, user_id: int, new_password: str) -> None:
    """Resetea la clave de un usuario. Lanza LookupError si no existe."""
    user = db.query(modelos.User).filter(modelos.User.id == user_id).first()
    if not user:
        raise LookupError("No encontrado")
    user.hashed_password = dependencias.get_db_hash(new_password)
    db.commit()
