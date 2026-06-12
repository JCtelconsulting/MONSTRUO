# ========================= scanner.py (v5.5 - FORCE FIXED) =========================
import logging
import os
import sys
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configuración ---
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_BASE_DIR = str(_PROJECT_ROOT / "data" / "files")
BASE_DIR = os.environ.get("BASE_FILES_DIR", _DEFAULT_BASE_DIR)

# Por defecto, si estamos en /srv/terreneitor_dev usa 8001; caso contrario 8000.
_DEFAULT_PORT = "8001" if "terreneitor_dev" in str(_PROJECT_ROOT) else "8000"
API_URL = (
    os.environ.get("TERRENEITOR_SCANNER_API_URL")
    or os.environ.get("SCANNER_API_URL")
    or f"http://127.0.0.1:{_DEFAULT_PORT}"
).rstrip("/")


def post_to_api(endpoint, data):
    try:
        response = requests.post(f"{API_URL}{endpoint}", json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning("WARN API %s: %s", endpoint, e)
        return None


def format_category_name(tipo_carpeta, nombre_carpeta):
    tipo = tipo_carpeta.upper().strip()
    nombre = nombre_carpeta.upper().strip()
    if nombre.startswith(tipo):
        nombre = nombre[len(tipo) :].lstrip(" -/_.")
    return nombre or "GENERAL"


def is_garbage(name):
    n = name.upper()
    return (".DUPE" in n) or ("1.4." in n) or n.startswith("_")


def scan_projects():
    logger.info("--- INICIANDO SCANNER v5.5 (MODO FORCE-FIX) ---")
    proyectos_procesados = {}
    categorias_procesadas = {}

    try:
        for root, dirs, files in os.walk(BASE_DIR, topdown=True):
            # FILTRO PREVENTIVO
            dirs[:] = [d for d in dirs if not is_garbage(d)]

            relative_path = os.path.relpath(root, BASE_DIR)
            if relative_path == ".":
                continue

            parts = Path(relative_path).parts
            if len(parts) == 3:
                nombre_pmc = parts[2].upper()
                if is_garbage(nombre_pmc):
                    continue
                if nombre_pmc not in proyectos_procesados:
                    logger.info(" [+] Registrando Proyecto: %s", nombre_pmc)
                    proyecto_data = {
                        "nombre_pmc": nombre_pmc,
                        "cliente": parts[0],
                        "area": parts[1],
                        "ruta_base": root,
                    }
                    db_proj = post_to_api("/proyectos/scanner/", proyecto_data)
                    if db_proj:
                        proyectos_procesados[nombre_pmc] = db_proj

            elif len(parts) == 5:
                nombre_pmc = parts[2].upper()
                if is_garbage(nombre_pmc):
                    continue
                db_proj = proyectos_procesados.get(nombre_pmc)
                if not db_proj:
                    continue
                nombre_final = format_category_name(parts[3], parts[4])
                cache_key = f"{db_proj.get('id')}-{nombre_final}"
                if cache_key not in categorias_procesadas:
                    cat_db = post_to_api(
                        "/categorias/scanner/",
                        {"nombre": nombre_final, "proyecto_id": db_proj.get("id")},
                    )
                    if cat_db:
                        categorias_procesadas[cache_key] = cat_db
                        logger.info("     > Cat: %s", nombre_final)

            elif len(parts) == 6:
                nombre_pmc = parts[2].upper()
                if is_garbage(nombre_pmc):
                    continue
                db_proj = proyectos_procesados.get(nombre_pmc)
                if not db_proj:
                    continue
                nombre_cat_padre = format_category_name(parts[3], parts[4])
                cat_db = categorias_procesadas.get(
                    f"{db_proj.get('id')}-{nombre_cat_padre}"
                )
                if cat_db and cat_db.get("id"):
                    item_data = {
                        "nombre": parts[5].upper(),
                        "ruta_item": root,
                        "categoria_id": cat_db.get("id"),
                    }
                    post_to_api("/items/scanner/", item_data)

        logger.info("--- SCANNER v5.5 FINALIZADO ---")
    except Exception as e:
        logger.exception("ERROR en scanner: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    scan_projects()
