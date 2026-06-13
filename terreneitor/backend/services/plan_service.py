"""Servicios para operaciones sobre PlanTrabajo y sus asignaciones."""

import shutil
from pathlib import Path

from sqlalchemy.orm import Session, selectinload

from terreneitor.backend import modelos, nucleo


def list_active_plans(db: Session) -> list[dict]:
    """Devuelve los planes con estado ABIERTO con sus asignaciones serializadas
    en el formato que espera el frontend de supervisor.
    """
    planes = (
        db.query(modelos.PlanTrabajo)
        .options(
            selectinload(modelos.PlanTrabajo.asignaciones)
            .selectinload(modelos.AsignacionPlan.item)
            .selectinload(modelos.Item.categoria)
            .selectinload(modelos.Categoria.proyecto),
            selectinload(modelos.PlanTrabajo.asignaciones).selectinload(
                modelos.AsignacionPlan.usuario
            ),
            selectinload(modelos.PlanTrabajo.asignaciones).selectinload(
                modelos.AsignacionPlan.colaboradores
            ),
            selectinload(modelos.PlanTrabajo.asignaciones).selectinload(
                modelos.AsignacionPlan.plan
            ),
        )
        .filter(modelos.PlanTrabajo.estado_plan == modelos.EstadoPlanEnum.ABIERTO)
        .all()
    )

    res = []
    for p in planes:
        asigs = [_serialize_asignacion(a) for a in p.asignaciones]
        asigs.sort(
            key=lambda x: (
                nucleo.natural_sort_key(x["categoria"]["proyecto"]["nombre_pmc"]),
                nucleo.natural_sort_key(x["item"]["nombre"]),
            )
        )
        res.append({"id": p.id, "descripcion": p.descripcion, "asignaciones": asigs})
    return res


def _serialize_asignacion(a: modelos.AsignacionPlan) -> dict:
    """Serializa una AsignacionPlan al shape que consume el frontend."""
    if a.colaboradores:
        usuarios = [modelos.UserSchema.model_validate(u) for u in a.colaboradores]
    elif a.usuario:
        # Fallback legado: si no hay colaboradores, usar la asignacion clasica.
        usuarios = [modelos.UserSchema.model_validate(a.usuario)]
    else:
        usuarios = []

    return {
        "id": a.id,
        "estado": a.estado.value,
        "item": {"id": a.item.id, "nombre": a.item.nombre.upper()},
        "categoria": {"proyecto": {"nombre_pmc": a.item.categoria.proyecto.nombre_pmc}},
        "usuario": (
            modelos.UserSchema.model_validate(a.usuario) if a.usuario else None
        ),
        "usuarios": usuarios,
    }


def delete_plan_cascade(db: Session, plan_id: int) -> None:
    """Borra un plan y todas sus asignaciones + asignaciones-usuarios
    (relacion N:M de cuadrilla). No toca filesystem."""
    asig_ids = [
        a[0]
        for a in db.query(modelos.AsignacionPlan.id)
        .filter(modelos.AsignacionPlan.plan_id == plan_id)
        .all()
    ]
    if asig_ids:
        db.query(modelos.AsignacionUsuario).filter(
            modelos.AsignacionUsuario.asignacion_id.in_(asig_ids)
        ).delete(synchronize_session=False)
    db.query(modelos.AsignacionPlan).filter(
        modelos.AsignacionPlan.plan_id == plan_id
    ).delete()
    db.query(modelos.PlanTrabajo).filter(modelos.PlanTrabajo.id == plan_id).delete()
    db.commit()


def archive_plan(db: Session, plan_id: int) -> dict:
    """Archiva un plan: cierra su estado y limpia carpetas de papelera
    asociadas a cada item del plan.

    Retorna {"status": "ok", "trash_deleted": int}. Lanza ValueError si
    el plan no existe.
    """
    plan = (
        db.query(modelos.PlanTrabajo).filter(modelos.PlanTrabajo.id == plan_id).first()
    )
    if not plan:
        raise ValueError(f"Plan {plan_id} no encontrado")

    asigs = (
        db.query(modelos.AsignacionPlan)
        .options(selectinload(modelos.AsignacionPlan.item))
        .filter(modelos.AsignacionPlan.plan_id == plan_id)
        .all()
    )

    deleted_dirs = 0
    with nucleo.plan_lock(plan_id):
        for a in asigs:
            if not a.item:
                continue
            root = Path(a.item.ruta_item)
            trash_dir = root / nucleo.TRASH_DIR_NAME / f"P{plan_id}"
            if trash_dir.exists():
                shutil.rmtree(trash_dir, ignore_errors=True)
                deleted_dirs += 1
            base_trash = root / nucleo.TRASH_DIR_NAME
            if base_trash.exists():
                try:
                    if not any(base_trash.iterdir()):
                        base_trash.rmdir()
                except Exception:
                    pass

    plan.estado_plan = modelos.EstadoPlanEnum.CERRADO
    db.commit()

    return {"status": "ok", "trash_deleted": deleted_dirs}
