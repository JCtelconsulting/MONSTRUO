# ========================= rutas_scanner.py =========================
# (P24) Contiene los endpoints del Scanner (/api/scanner y /proyectos/scanner)
# ===========================================================
import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

# (P24.1) FIX: Importaciones Absolutas (quitar el '.')
from backend import dependencias, modelos, nucleo

# Router para /api/scanner (protegido)
router_api = APIRouter(
    prefix="/api/scanner",
    tags=["Scanner"],
    dependencies=[Depends(dependencias.require_admin)],
)


def _require_loopback(request: Request):
    """Solo permite llamadas desde el propio servidor (scanner.py local).

    Sin esto, estos endpoints de escritura quedaban abiertos a Internet via el
    proxy. El contenedor no corre con --proxy-headers, asi que request.client.host
    es la IP TCP real (no falsificable por cabeceras).
    """
    client_host = request.client.host if request.client else None
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="Solo acceso interno (loopback)")


# Router para /.../scanner (endpoints internos, restringidos a loopback)
router_interno = APIRouter(
    tags=["Scanner (interna)"],
    dependencies=[Depends(_require_loopback)],
)


def _is_under_base(path: str, base_dir: str) -> bool:
    if not path or not base_dir:
        return False
    p = os.path.normpath(path)
    b = os.path.normpath(base_dir)
    return p == b or p.startswith(b + os.sep)


@router_api.post("/run")
async def run_scanner_endpoint(db: Session = Depends(dependencias.get_db)):
    # 1. Ejecutar Script Externo (OCC / Scanner físico)
    try:
        process = await asyncio.create_subprocess_exec(
            nucleo.PYTHON_EXECUTABLE,
            nucleo.SCANNER_SCRIPT_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()
        _log_stdout = _stdout.decode().strip()
        log_stderr = stderr.decode().strip()
        if process.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Error al ejecutar scanner: {log_stderr or 'Error desconocido'}",
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al iniciar scanner: {e}")

    # 2. Limpieza de Base de Datos (Items Huérfanos)
    try:
        if not os.path.exists(nucleo.BASE_FILES_DIR):
            print(
                f"CRITICAL: No se detecta {nucleo.BASE_FILES_DIR}. Abortando limpieza DB.",
                flush=True,
            )
            raise HTTPException(
                status_code=500,
                detail="PAN... archivos desconectado. Limpieza abortada para proteger datos.",
            )
        items_db = db.query(modelos.Item).all()
        items_borrados = 0
        for item in items_db:
            if not os.path.exists(item.ruta_item):
                db.query(modelos.AsignacionPlan).filter(
                    modelos.AsignacionPlan.item_id == item.id
                ).delete()
                db.delete(item)
                items_borrados += 1
        db.commit()
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error limpiando ítems huérfanos: {e}"
        )
    return {
        "status": "ok",
        "message": f"Scanner ejecutado y {items_borrados} ítems huérfanos eliminados.",
    }


# --- Endpoints Internos ---


@router_interno.post("/proyectos/scanner/")
def scanner_add_proyecto(
    req: modelos.ProyectoCreate, db: Session = Depends(dependencias.get_db)
):
    if req.ruta_base and not _is_under_base(req.ruta_base, nucleo.BASE_FILES_DIR):
        raise HTTPException(status_code=400, detail="ruta_base fuera de BASE_FILES_DIR")
    existing = (
        db.query(modelos.Proyecto)
        .filter(modelos.Proyecto.nombre_pmc == req.nombre_pmc)
        .first()
    )
    if existing:
        return {"status": "exists", "id": existing.id}
    new_proyecto = modelos.Proyecto(**req.model_dump())
    db.add(new_proyecto)
    db.commit()
    db.refresh(new_proyecto)
    return {"status": "created", "id": new_proyecto.id}


@router_interno.post("/categorias/scanner/")
def scanner_add_categoria(
    req: modelos.CategoriaCreate, db: Session = Depends(dependencias.get_db)
):
    existing = (
        db.query(modelos.Categoria)
        .filter(
            modelos.Categoria.nombre == req.nombre,
            modelos.Categoria.proyecto_id == req.proyecto_id,
        )
        .first()
    )
    if existing:
        return {"status": "exists", "id": existing.id}
    new_categoria = modelos.Categoria(**req.model_dump())
    db.add(new_categoria)
    db.commit()
    db.refresh(new_categoria)
    return {"status": "created", "id": new_categoria.id}


@router_interno.post("/items/scanner/")
def scanner_add_item(
    req: modelos.ItemCreate, db: Session = Depends(dependencias.get_db)
):
    if req.ruta_item and not _is_under_base(req.ruta_item, nucleo.BASE_FILES_DIR):
        raise HTTPException(status_code=400, detail="ruta_item fuera de BASE_FILES_DIR")
    existing = (
        db.query(modelos.Item).filter(modelos.Item.ruta_item == req.ruta_item).first()
    )
    if existing:
        existing.nombre = req.nombre
        db.commit()
        return {"status": "updated", "id": existing.id}
    new_item = modelos.Item(**req.model_dump())
    db.add(new_item)
    db.commit()
    return {"status": "created", "id": new_item.id}
