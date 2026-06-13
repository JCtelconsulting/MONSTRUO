#!/usr/bin/env python3
# cleanup_reloaded.py
# Script mejorado para limpiar duplicados y normalizar nombres.
#
# OBJETIVO:
# 1. Detectar carpetas con nombres "sucios" (tildes, espacios raros, minusculas mixtas).
# 2. Calcular nombre "NORMALIZADO" (Mayusculas, sin tildes, ASCII).
# 3. Si existe AMBOS (sucio y normalizado):
#    - MOVER contenido de Sucio -> Normalizado.
#    - BORRAR Sucio (si queda vacio).
# 4. Si solo existe Sucio:
#    - RENOMBRAR Sucio -> Normalizado.
# 5. Si solo existe Normalizado:
#    - No hacer nada.

import argparse
import os
import re
import shutil
import time
import unicodedata

# --- CONFIGURACION ---
LOG_FILE = "cleanup_reloaded.log"
TRASH_DIR_NAME = ".dupe_trash_auto"


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} - {msg}"
    print(line)
    try:
        # Guardar en el directorio actual donde se ejecuta el script
        log_path = os.path.abspath(LOG_FILE)

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Error escribiendo log: {e}")


def normalize_name(name):
    """
    Convierte 'Camión de Medición' -> 'CAMION_DE_MEDICION'
    """
    if not isinstance(name, str):
        name = os.fsdecode(name)

    # 1. Decodificar unicode
    try:
        name_u = name.encode("utf-8", "surrogatepass").decode("utf-8", "replace")
    except Exception:
        name_u = name

    # 2. Descomponer tildes (NFD) y eliminar caracteres de combinacion (tildes)
    n = unicodedata.normalize("NFKD", name_u)
    n = "".join(ch for ch in n if not unicodedata.combining(ch))

    # 3. A ASCII estricto
    n = n.encode("ascii", "ignore").decode("ascii")

    # 4. Reemplazar caracteres no alfanumericos por guion bajo
    n = re.sub(r"[^A-Za-z0-9]+", "_", n)

    # 5. A mayusculas
    n = n.upper()

    # 6. Eliminar guiones bajos extras al inicio/fin o repetidos
    n = re.sub(r"_+", "_", n).strip("_")

    return n


def get_unique_trash_path(trash_root, filename):
    base, ext = os.path.splitext(filename)
    ts = time.strftime("%Y%m%d_%H%M%S")
    name = f"{base}_{ts}{ext}"
    return os.path.join(trash_root, name)


def merge_folders(src, dst, trash_root, apply=False):  # noqa: C901
    """
    Mueve todo de src a dst. Si hay conflictos de archivo, renombra el de src antes de mover.
    """
    log(f"   [MERGE] Iniciando fusion: {src} -> {dst}")

    if not os.path.isdir(src):
        return

    items = os.listdir(src)
    if not items:
        # Carpeta vacia, la borramos
        log(f"   [RMDIR] Carpeta vacia eliminada: {src}")
        if apply:
            os.rmdir(src)
        return

    for item in items:
        s_item = os.path.join(src, item)
        d_item = os.path.join(dst, item)

        if os.path.exists(d_item):
            # CONFLICTO
            if os.path.isdir(s_item):
                # Si ambos son directorios, recursividad
                merge_folders(s_item, d_item, trash_root, apply)
            else:
                # Archivo vs Archivo (o Dir)
                # Renombrar source y mover
                base, ext = os.path.splitext(item)
                new_name = f"{base}_DUPE_{int(time.time()*1000)}{ext}"
                d_item_new = os.path.join(dst, new_name)
                log(
                    f"   [CONFLICTO] Archivo {item} ya existe. Renombrando a {new_name}"
                )
                if apply:
                    shutil.move(s_item, d_item_new)
        else:
            # No conflicto, mover directo
            log(f"   [MOVE] {item} -> {dst}")
            if apply:
                shutil.move(s_item, d_item)

    # Al final, si src quedo vacia, borrar
    if apply:
        try:
            if not os.listdir(src):
                os.rmdir(src)
                log(f"   [RMDIR] Carpeta origen eliminada tras fusion: {src}")
            else:
                log(
                    f"   [WARN] Carpeta origen NO quedo vacia (no se pudo borrar): {src}"
                )
        except Exception as e:
            log(f"   [ERROR] Al borrar carpeta origen {src}: {e}")


def process_directory(root_path, apply=False, only_targets=None):  # noqa: C901
    log(f"Escanenando: {root_path}")

    trash_root = os.path.join(root_path, TRASH_DIR_NAME)
    if apply:
        os.makedirs(trash_root, exist_ok=True)

    # Listar directorios en root
    try:
        dirs = [
            d
            for d in os.listdir(root_path)
            if os.path.isdir(os.path.join(root_path, d))
        ]
    except PermissionError:
        log(f"ERROR: Permiso denegado leyendo {root_path}")
        return

    # Agrupar por nombre normalizado
    # Key: NOMBRE_NORMALIZADO -> Value: LISTA DE NOMBRES REALES
    groups = {}
    for d in dirs:
        if d == TRASH_DIR_NAME:
            continue
        norm = normalize_name(d)
        if norm not in groups:
            groups[norm] = []
        groups[norm].append(d)

    # Filtrar si hay targets especificos (Solo en el nivel raiz o si se desea propagar logicamente,
    # pero aqui asumimos que el usuario filtra las carpetas principales)
    if only_targets:
        normalized_targets = [normalize_name(t) for t in only_targets]
        # Filtramos los grupos que NO coincidan con los targets
        groups = {k: v for k, v in groups.items() if k in normalized_targets}
        if not groups:
            log(f"WARN: No se encontraron carpetas que coincidan con {only_targets}")

    for norm, real_names in groups.items():
        if not norm:
            continue  # Skip if empty

        # Caso ideal: Solo hay 1 carpeta y ya esta normalizada
        if len(real_names) == 1 and real_names[0] == norm:
            # Aun asi podriamos querer entrar recursivamente si es que queremos limpiar subniveles
            pass
        else:
            log(f"Procesando grupo '{norm}': {real_names}")

        # Identificar si existe la carpeta "Target" (la normalizada exacta)
        target_path = os.path.join(root_path, norm)
        target_exists = norm in real_names

        # Si NO existe la target, elegimos la mejor candidata para SER la target (renombrandola)
        if not target_exists:
            # Tomamos la primera como base (o la mas parecida)
            candidate = real_names[0]
            candidate_path = os.path.join(root_path, candidate)

            log(f" -> Target '{norm}' NO existe. Renombrando '{candidate}' -> '{norm}'")
            if apply:
                try:
                    os.rename(candidate_path, target_path)
                    # Ahora la target existe y es esta
                    target_exists = True
                    # Removemos la candidate de la lista de pendientes por procesar
                    real_names.remove(candidate)
                    # Agregamos la nueva target (aunque ya no la procesaremos en este loop de real_names, sirve de referencia)
                except Exception as e:
                    log(f"ERROR Fatal renombrando {candidate} a {norm}: {e}")
                    continue

        # Ahora, para todas las RESTANTES en real_names, debemos mover su contenido a target_path
        # (Si acabamos de renombrar, real_names tiene el resto. Si ya existia, real_names incluye la target, hay que sacarla)

        for name in real_names:
            if name == norm:
                continue  # Es la target, no se mueve a si misma

            src_path = os.path.join(root_path, name)
            log(f" -> Fusionando '{name}' hacia '{norm}'")

            merge_folders(src_path, target_path, trash_root, apply)

    # Recursividad: entrar a los directorios (ahora normalizados o existentes)
    # Si filtramos por targets, solo entramos a esos targets en este nivel.
    # Para subniveles, pasamos only_targets=None para limpiar TODO el contenido interno de esa carpeta.

    dirs_to_scan = []
    if only_targets:
        # Solo escaneamos las carpetas que acabamos de procesar/validar que coinciden con el target
        for norm in groups.keys():
            if os.path.isdir(os.path.join(root_path, norm)):
                dirs_to_scan.append(norm)
    else:
        # Si no hubo filtro, escaneamos todo
        if apply:
            dirs_to_scan = [
                d
                for d in os.listdir(root_path)
                if os.path.isdir(os.path.join(root_path, d)) and d != TRASH_DIR_NAME
            ]
        else:
            dirs_to_scan = [d for d in dirs if d != TRASH_DIR_NAME]

    for d in dirs_to_scan:
        sub_path = os.path.join(root_path, d)
        # Limpieza profunda sin filtro (dentro de Sonda queremos limpiar todo)
        # Cuidado: si pasamos only_targets=None, limpiara todo adentro. Correcto.
        process_directory(sub_path, apply, only_targets=None)


def main():
    parser = argparse.ArgumentParser(description="Limpieza y Normalizacion de Carpetas")
    parser.add_argument("root_path", help="Ruta raiz a escanear")
    parser.add_argument(
        "--apply", action="store_true", help="Aplicar cambios (sin esto es DRY RUN)"
    )
    parser.add_argument(
        "--only",
        nargs="+",
        help="Lista de nombres de carpetas especificas a procesar (ej: Sonda Ricoh)",
    )  # Nuevo argumento

    args = parser.parse_args()

    if not os.path.exists(args.root_path):
        print(f"Ruta no existe: {args.root_path}")
        return

    log("=== INICIO CLEANUP RELOADED ===")
    log(f"ROOT: {args.root_path}")
    log(f"MODE: {'APPLY (Escritura Real)' if args.apply else 'DRY RUN (Solo lectura)'}")
    if args.only:
        log(f"FILTER: Solo procesando carpetas que coincidan con: {args.only}")

    process_directory(args.root_path, args.apply, only_targets=args.only)

    log("=== FIN ===")


if __name__ == "__main__":
    main()
