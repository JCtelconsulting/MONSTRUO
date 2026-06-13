# reparar_claves.py
# Utility one-shot para resetear las claves de todos los usuarios.
# La nueva clave se toma de la variable de entorno TERRENEITOR_RESET_PASSWORD,
# por defecto "1234". No borra tareas, proyectos ni fotos.
import logging
import os

from terreneitor.backend.core import dependencias, nucleo
from terreneitor.backend.models import modelos

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def reparar() -> None:
    clave_temporal = os.environ.get("TERRENEITOR_RESET_PASSWORD", "1234")
    logger.info("--- Iniciando Reparacion de Claves (Preservando Datos) ---")

    db = nucleo.SessionLocal()
    try:
        usuarios = db.query(modelos.User).all()
        logger.info("Usuarios encontrados: %d", len(usuarios))

        nuevo_hash = dependencias.get_db_hash(clave_temporal)
        for u in usuarios:
            logger.info(" -> Reparando clave para: %s", u.email)
            u.hashed_password = nuevo_hash

        db.commit()
        logger.info(
            "LISTO. %d usuarios actualizados con clave '%s'.",
            len(usuarios),
            clave_temporal,
        )
    except Exception:
        logger.exception("ERROR reparando claves")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    reparar()
