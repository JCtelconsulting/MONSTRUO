#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# --- CONFIGURACION ---
# Asegurate que esta ruta sea EXACTAMENTE donde estan tus carpetas de cliente
BASE_PROJECTS_DIR = "/srv/terreneitor/data/files"
LOG_FILE = "/srv/terreneitor/logs/crear_estructura.log"
MAX_DEPTH = 3
DEFAULT_SCANNER_SCRIPT = os.environ.get(
    "SCANNER_SCRIPT_PATH",
    str(Path(__file__).resolve().parents[1] / "utils" / "scanner.py"),
)

# --- DEFINICION DE ESTRUCTURAS ---
STRUCTURE_TEMPLATES = {
    "PMC": [
        "EDP/1.0 Obras Civiles/1.01 OOCC Fundacion",
        "EDP/1.0 Obras Civiles/1.02 Instalacion Poste y Brazo sobre Fundacion",
        "EDP/1.0 Obras Civiles/1.03 Instalacion Puesta a Tierra",
        "EDP/1.0 Obras Civiles/1.04 Cambio de Postes y Reparacion de Fundacion",
        "EDP/1.0 Obras Civiles/1.05 Relleno de excavaciones",
        "EDP/1.0 Obras Civiles/1.06 Ductos de canalizaciones PVC2",
        "EDP/1.0 Obras Civiles/1.07 Metro lineal de conexion aerea",
        "EDP/1.0 Obras Civiles/1.08 Instalacion de camaras electricas subterranea",
        "EDP/1.0 Obras Civiles/1.09 Reposicion de Panos de Hormigon",
        "EDP/1.0 Obras Civiles/1.10 Demolicion de dados de hormigon",
        "EDP/1.0 Obras Civiles/1.11 Aumento de demolicion y reposicion",
        "EDP/1.0 Obras Civiles/1.12 Refuerzos de hormigon por M3",
        "EDP/1.0 Obras Civiles/1.13 Reposicion de Baldosas, incluye excavacion",
        "EDP/1.0 Obras Civiles/1.14 Provision e instalacion de baldosas por M2",
        "EDP/1.0 Obras Civiles/1.15 Restitucion de acera o solera",
        "EDP/1.0 Obras Civiles/1.16 Cambio de soleras por metro lineal",
        "EDP/1.0 Obras Civiles/1.17 Retiro de escombros por M3",
        "EDP/1.0 Obras Civiles/1.18 Sobre excavacion por M2",
        "EDP/1.0 Obras Civiles/1.19 Agotamiento de napas freaticas",
        "EDP/1.0 Obras Civiles/1.20 Mitigacion extra por metro lineal",
        "EDP/1.0 Obras Civiles/1.21 Cerco duro para proteger excavaciones",
        "EDP/2.0 Instalaciones Electricas/2.01 OOCC Empalme electrico hasta 10 metros",
        "EDP/2.0 Instalaciones Electricas/2.02 Metro lineal de trabajos electricos",
        "EDP/2.0 Instalaciones Electricas/2.03 Reposicion de cableado electrico de medidor",
        "EDP/2.0 Instalaciones Electricas/2.04 Cambio de Diferencial 25A",
        "EDP/2.0 Instalaciones Electricas/2.05 Cambio de Automatico 16A",
        "EDP/2.0 Instalaciones Electricas/2.06 Cambio de Automatico de 16A para medidor",
        "EDP/2.0 Instalaciones Electricas/2.07 Ferreteria que instalar en poste y brazos",
        "EDP/2.0 Instalaciones Electricas/2.08 Fijaciones en poste",
        "EDP/2.0 Instalaciones Electricas/2.09 Flexibles, terminales y coplas",
        "EDP/3.0 Equipos y Conectividad/3.01 Implementacion Airmobile en 8 dias",
        "EDP/3.0 Equipos y Conectividad/3.02 Implementacion Satlink en 10 dias",
        "EDP/3.0 Equipos y Conectividad/3.03 Instalacion 1 Antena MMOO y PANEO",
        "EDP/3.0 Equipos y Conectividad/3.04 Revision radioenlaces en 1 poste RM",
        "EDP/3.0 Equipos y Conectividad/3.05 Kit Antena Punto a Punto",
        "EDP/3.0 Equipos y Conectividad/3.06 Kit antena punto multipunto",
        "EDP/3.0 Equipos y Conectividad/3.07 Paneo y Configuracion de Antena",
        "EDP/3.0 Equipos y Conectividad/3.08 Cambio de Antena",
        "EDP/3.0 Equipos y Conectividad/3.09 Instalacion 1 camara en Poste de Santiago",
        "EDP/3.0 Equipos y Conectividad/3.10 Paneo y regulacion de Camara",
        "EDP/3.0 Equipos y Conectividad/3.11 Recambio de Camaras",
        "EDP/3.0 Equipos y Conectividad/3.12 Cambio de cable CAT6 blindado",
        "EDP/3.0 Equipos y Conectividad/3.13 Cambio de Patch Cord CAT6",
        "EDP/3.0 Equipos y Conectividad/3.14 Gabinete de intercomunicacion armado",
        "EDP/3.0 Equipos y Conectividad/3.15 Gateway celular LTE 4G 5-port",
        "EDP/3.0 Equipos y Conectividad/3.16 Switch ethernet Gigabit industrial",
        "EDP/3.0 Equipos y Conectividad/3.17 Cambio de Cableado de circuitos internos",
        "EDP/3.0 Equipos y Conectividad/3.18 Recambio de UPS",
        "EDP/3.0 Equipos y Conectividad/3.19 Cambio fuente de poder de Switch",
        "EDP/3.0 Equipos y Conectividad/3.20 MDR-60-48. MEANWELL",
        "EDP/3.0 Equipos y Conectividad/3.21 POE para camara o antena",
        "EDP/3.0 Equipos y Conectividad/3.22 Fuente de Poder",
        "EDP/4.0 Servicios y Soporte/4.01 Servicio MPLS 100 Mbps",
        "EDP/4.0 Servicios y Soporte/4.02 Activacion MPLS en 10 dias",
        "EDP/4.0 Servicios y Soporte/4.03 Servicio Airmobile velocidad 4G-5G (BE)",
        "EDP/4.0 Servicios y Soporte/4.04 Servicio Satlink 100-20 Mbps",
        "EDP/4.0 Servicios y Soporte/4.05 Servicio de Camion Alza Hombre por Hora",
        "EDP/4.0 Servicios y Soporte/4.06 Traslado Alza hombre por vez de uso",
        "EDP/4.0 Servicios y Soporte/4.07 RRHH Cuadrilla 3 Personas",
        "EDP/4.0 Servicios y Soporte/4.08 Gestion urgencia en 1 poste RM 24-7",
        "EDP/4.0 Servicios y Soporte/4.09 Tiempos muertos por ausencia de permisos",
        "EDP/4.0 Servicios y Soporte/4.10 Tramites y registro SERVIU",
        "EDP/5.0 Componentes y Mantenimiento General/5.01 Movimiento y regulacion de soportes",
        "EDP/5.0 Componentes y Mantenimiento General/5.02 Cambio de flexible de Gabinete a Poste",
        "EDP/5.0 Componentes y Mantenimiento General/5.03 Cambio de flexible de Brazo a Poste",
        "EDP/5.0 Componentes y Mantenimiento General/5.04 Cambio de flexible de caja a Brazo",
        "EDP/5.0 Componentes y Mantenimiento General/5.05 Cambio de Ventilador",
        "EDP/5.0 Componentes y Mantenimiento General/5.06 Cambio Termostato accionador de Ventiladores",
        "EDP/5.0 Componentes y Mantenimiento General/5.07 Sellado e Impermeabilizacion de cajas y ductos",
        "INFORME/OBRA CIVIL/1.1. PERMISOS",
        "INFORME/OBRA CIVIL/1.2. ESCOMBROS",
        "INFORME/OBRA CIVIL/1.3. SEGREGACION",
        "INFORME/OBRA CIVIL/1.4. SENALETICAS",
        "INFORME/OBRA CIVIL/2.1. PUNTO EXCAVACION (PREVIO)",
        "INFORME/OBRA CIVIL/2.2. INFORME SONDAJE",
        "INFORME/OBRA CIVIL/2.3. EXCAVACION",
        "INFORME/OBRA CIVIL/2.4. MALLA",
        "INFORME/OBRA CIVIL/2.8. LETREROS OCCC",
        "INFORME/OBRA CIVIL/2.9. HORMIGON",
        "INFORME/OBRA CIVIL/2.12. PAVIMENTO Y TERMINACIONES",
        "INFORME/OBRA CIVIL/2.14. HOLGURA",
        "INFORME/INSTALACIONES/3.1. SIST. SUJECCION ADOSADO",
        "INFORME/INSTALACIONES/3.2. IZAMIENTO POSTE",
        "INFORME/INSTALACIONES/3.3. DUCTOS",
        "INFORME/INSTALACIONES/3.4. BARRA COPPERWELD",
        "INFORME/INSTALACIONES/3.5. VALIDACION TORQUE POSTE",
        "INFORME/INSTALACIONES/3.6. FLEXIBLES",
        "INFORME/INSTALACIONES/3.7. APOYO ESCALA",
        "INFORME/INSTALACIONES/3.8. TABLERO DISTRIBUCION",
        "INFORME/INSTALACIONES/3.9. REGLETAS ELECTRICAS",
        "INFORME/INSTALACIONES/3.10. SWITCH COM. INDUSTRIAL",
        "INFORME/INSTALACIONES/3.11. POE",
        "INFORME/INSTALACIONES/3.12. ANPR",
        "INFORME/INSTALACIONES/3.13. PTZ",
        "INFORME/INSTALACIONES/3.14. SWITCH AP",
        "INFORME/INSTALACIONES/3.15. CENAFAS",
        "INFORME/INSTALACIONES/3.16. PINTURA ANTI OXIDO",
        "INFORME/INSTALACIONES/3.17. LUZ PILOTO",
        "INFORME/INSTALACIONES/3.18. VENTILADOR",
        "INFORME/INSTALACIONES/3.19. QR",
        "INFORME/INSTALACIONES/3.20. ROTULACION DE CABLES",
        "INFORME/INSTALACIONES/3.21. ETIQUETADO BOCA SWITCH",
        "INFORME/INSTALACIONES/3.22. ETIQUETADO SALIDA UPS",
        "INFORME/INSTALACIONES/3.23. ETIQUETADO FUENTE ALIMENTACION",
        "INFORME/INSTALACIONES/3.24. CAJA ESTANCA",
        "INFORME/INSTALACIONES/3.26. ROSETAS",
        "INFORME/INSTALACIONES/3.27. ANTENA",
    ],
    "SATLINK": [
        "SATLINK/LEVANTAMIENTO/1.01 LEVANTAMIENTO Y PLANIFICACION",
        "SATLINK/INSTALACION/2.01 INSTALACION DE ANTENA EN TECHUMBRE",
        "SATLINK/CANALIZACION/3.01 CANALIZACION EXTERNA Y CONEXIONES",
        "SATLINK/CANALIZACION/4.01 LLEGADA A RACK Y EQUIPOS INTERIORES",
        "SATLINK/PRUEBAS/5.01 PRUEBAS Y PUESTA EN MARCHA",
        "SATLINK/CIERRE/6.01 LIMPIEZA Y ORDENAMIENTO",
    ],
    "OBRA": [
        "OBRA/0.0 MOVILIZACION/0.01 SALIDA DE OFICINA",
        "OBRA/0.0 MOVILIZACION/0.02 LLEGADA A TERRENO",
        "OBRA/0.0 MOVILIZACION/0.03 SALIDA DE TERRENO",
        "OBRA/0.0 MOVILIZACION/0.04 LLEGADA A OFICINA",
        "OBRA/1.0 PREPARACION/1.01 LEVANTAMIENTO INICIAL",
        "OBRA/1.0 PREPARACION/1.02 PROTECCION DE AREAS",
        "OBRA/1.0 PREPARACION/1.03 SENALIZACION Y CIERRE DE AREA",
        "OBRA/1.0 PREPARACION/1.04 DESARME RETIRO DE ELEMENTOS",
        "OBRA/2.0 DEMOLICION Y RETIRO/2.01 DEMOLICION LIVIANA",
        "OBRA/2.0 DEMOLICION Y RETIRO/2.02 RETIRO DE ESCOMBROS",
        "OBRA/2.0 DEMOLICION Y RETIRO/2.03 GESTION DE RESIDUOS Y DISPOSICION",
        "OBRA/3.0 MOVIMIENTO DE TIERRA/3.01 EXCAVACIONES",
        "OBRA/3.0 MOVIMIENTO DE TIERRA/3.02 RETIRO DE MATERIAL",
        "OBRA/3.0 MOVIMIENTO DE TIERRA/3.03 RELLENO",
        "OBRA/3.0 MOVIMIENTO DE TIERRA/3.04 NIVELACION",
        "OBRA/3.0 MOVIMIENTO DE TIERRA/3.05 COMPACTACION",
        "OBRA/4.0 OBRA CIVIL/4.01 REPARACION DE MUROS Y GRIETAS",
        "OBRA/4.0 OBRA CIVIL/4.02 ALBANILERIA MENOR",
        "OBRA/4.0 OBRA CIVIL/4.03 ESTUCO Y REPARACIONES",
        "OBRA/4.0 OBRA CIVIL/4.04 IMPERMEABILIZACION PUNTOS CRITICOS",
        "OBRA/5.0 BANOS Y SANITARIOS/5.01 REPARACION DE BANO",
        "OBRA/5.0 BANOS Y SANITARIOS/5.02 CAMBIO ARTEFACTOS Y GRIFERIA",
        "OBRA/5.0 BANOS Y SANITARIOS/5.03 REVISION FILTRACIONES",
        "OBRA/5.0 BANOS Y SANITARIOS/5.04 PRUEBA ESTANQUEIDAD",
        "OBRA/5.0 BANOS Y SANITARIOS/5.05 SOLERILLA ALREDEDOR DE BANOS",
        "OBRA/6.0 ELECTRICIDAD/6.01 REVISION TABLERO Y PROTECCIONES",
        "OBRA/6.0 ELECTRICIDAD/6.02 REVISION CIRCUITO ELECTRICO",
        "OBRA/6.0 ELECTRICIDAD/6.03 PUESTA A TIERRA",
        "OBRA/6.0 ELECTRICIDAD/6.04 CANALIZACION",
        "OBRA/6.0 ELECTRICIDAD/6.05 CABLEADO",
        "OBRA/6.0 ELECTRICIDAD/6.06 TOMAS Y ENCHUFES",
        "OBRA/6.0 ELECTRICIDAD/6.07 ILUMINACION LUMINARIAS",
        "OBRA/6.0 ELECTRICIDAD/6.08 PRUEBAS CONTINUIDAD Y FUNCIONAMIENTO",
        "OBRA/7.0 TECHUMBRE/7.01 ESTRUCTURA TECHO",
        "OBRA/7.0 TECHUMBRE/7.02 IMPERMEABILIZACION",
        "OBRA/7.0 TECHUMBRE/7.03 AISLACION SI APLICA",
        "OBRA/7.0 TECHUMBRE/7.04 CANALETAS Y BAJADAS",
        "OBRA/8.0 TERMINACIONES/8.01 LIMPIEZA DE MURALLAS",
        "OBRA/8.0 TERMINACIONES/8.02 PREPARACION SUPERFICIES",
        "OBRA/8.0 TERMINACIONES/8.03 PINTURA",
        "OBRA/8.0 TERMINACIONES/8.04 REVESTIMIENTOS SI APLICA",
        "OBRA/8.0 TERMINACIONES/8.05 PISOS SI APLICA",
        "OBRA/8.0 TERMINACIONES/8.06 SELLADOS Y REMATES",
        "OBRA/9.0 CIERRE/9.01 LIMPIEZA FINAL",
        "OBRA/9.0 CIERRE/9.02 RETIRO DE RESIDUOS FINAL",
        "OBRA/9.0 CIERRE/9.03 CHECKLIST ENTREGA",
        "OBRA/9.0 CIERRE/9.04 REGISTRO FOTOGRAFICO FINAL",
        "SEGURIDAD/10.0 PLAN Y EPP/10.01 CHARLA SEGURIDAD",
        "SEGURIDAD/10.0 PLAN Y EPP/10.02 EPP",
        "SEGURIDAD/10.0 PLAN Y EPP/10.03 PERMISOS DE TRABAJO",
        "SEGURIDAD/10.0 PLAN Y EPP/10.04 PUNTAS TIPO TIBURON EN PORTON",
        "SEGURIDAD/10.0 PLAN Y EPP/10.05 SOPORTES PARA SERPENTINA DE SEGURIDAD",
        "MATERIALES/11.0 RECEPCION/11.01 RECEPCION MATERIALES",
        "MATERIALES/11.0 RECEPCION/11.02 GUIAS Y FACTURAS",
        "MATERIALES/11.0 RECEPCION/11.03 ACOPIO Y ORDEN",
        "CALIDAD/12.0 CONTROL/12.01 INSPECCION PREVIAS",
        "CALIDAD/12.0 CONTROL/12.02 INSPECCION EN PROCESO",
        "CALIDAD/12.0 CONTROL/12.03 INSPECCION FINAL",
        "ADMIN/13.0 GESTION/13.01 ACTA INICIO",
        "ADMIN/13.0 GESTION/13.02 MINUTAS",
        "ADMIN/13.0 GESTION/13.03 COORDINACIONES",
        "ADMIN/13.0 GESTION/13.04 FOTOS GENERALES",
    ],
    "DOMICILIO": [
        "DOMICILIO/1.0 EXTERIOR/1.01 CUENTA DE CTO",
        "DOMICILIO/1.0 EXTERIOR/1.02 POTENCIA CTO",
        "DOMICILIO/1.0 EXTERIOR/1.03 TAZO CLIENTE",
        "DOMICILIO/1.0 EXTERIOR/1.04 FOTO ACOMETIDA",
        "DOMICILIO/2.0 TENDIDO Y LLEGADA/2.01 CABLEADO ADOSADO",
        "DOMICILIO/2.0 TENDIDO Y LLEGADA/2.02 TENSION DE FIBRA",
        "DOMICILIO/3.0 INSTALACION INTERIOR/3.01 CAJA DE CONECTORES (PTO)",
        "DOMICILIO/3.0 INSTALACION INTERIOR/3.02 POTENCIA CAJA INTERIOR",
        "DOMICILIO/4.0 EQUIPOS FINAL/4.01 ROUTER",
        "DOMICILIO/4.0 EQUIPOS FINAL/4.02 DECODIFICADORES",
        "DOMICILIO/4.0 EQUIPOS FINAL/4.03 PRUEBAS DE SERVICIO",
    ],
    "LEVANTAMIENTO": [
        "LEVANTAMIENTO/FISICO/1.01 UBICACION RACK O GABINETE",
        "LEVANTAMIENTO/FISICO/1.02 ESTADO RACK O GABINETE",
        "LEVANTAMIENTO/FISICO/1.03 CABLEADO Y CATEGORIA",
        "LEVANTAMIENTO/FISICO/1.04 CONECTORES Y PATCH CORDS",
        "LEVANTAMIENTO/FISICO/1.05 CANALIZACIONES",
        "LEVANTAMIENTO/FISICO/1.06 CONEXIONES ELECTRICAS DISPONIBLES",
        "LEVANTAMIENTO/FISICO/1.07 ESTADO DE EQUIPOS",
        "LEVANTAMIENTO/RED/2.01 MARCA MODELO Y SERIE DE EQUIPO",
        "LEVANTAMIENTO/RED/2.02 CONSUMOS Y POTENCIA",
        "LEVANTAMIENTO/RED/2.03 CONFIGURACION ACTUAL",
        "LEVANTAMIENTO/RED/2.04 TROUBLESHOOTING",
    ],
}


def log_msg(msg):
    """Imprime en consola y guarda en log."""
    print(msg, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    except Exception as e:
        print(f"Error escribiendo log: {e}")


def run_storage_scan():
    scanner_script = DEFAULT_SCANNER_SCRIPT
    if not scanner_script or not os.path.exists(scanner_script):
        log_msg(f"WARNING: scanner no encontrado: {scanner_script}")
        return

    python_exec = os.environ.get("PYTHON_EXECUTABLE") or sys.executable or "python3"
    log_msg(f" -> Ejecutando scanner: {python_exec} {scanner_script}")
    try:
        result = subprocess.run(
            [python_exec, scanner_script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            log_msg(f" -> ERROR scanner (rc={result.returncode}): {details}")
        else:
            log_msg(" -> Scanner finalizado.")
    except Exception as e:
        log_msg(f" -> ERROR ejecutando scanner: {e}")


def normalize_dir_name(name):
    return "".join(ch for ch in name.lower() if ch.isalnum())


def get_template_markers(template):
    markers = set()
    for entry in template:
        markers.add(entry.split("/", 1)[0])
    return markers


TEMPLATE_MARKERS = {
    key: get_template_markers(template) for key, template in STRUCTURE_TEMPLATES.items()
}
SAFE_TEMPLATES = {"PMC", "OBRA", "SATLINK", "DOMICILIO", "LEVANTAMIENTO"}


def has_existing_structure(project_path, template_name):
    markers = TEMPLATE_MARKERS.get(template_name)
    if not markers:
        return False
    try:
        entries = [
            d
            for d in os.listdir(project_path)
            if os.path.isdir(os.path.join(project_path, d))
        ]
    except Exception:
        return False
    existing_norm = {normalize_dir_name(d) for d in entries}
    for marker in markers:
        marker_norm = normalize_dir_name(marker)
        for existing in existing_norm:
            if (
                existing == marker_norm
                or existing.startswith(marker_norm)
                or marker_norm.startswith(existing)
            ):
                return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crear estructura de proyectos")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo muestra cambios, no crea ni renombra",
    )
    parser.add_argument(
        "--append-missing",
        action="store_true",
        help="Agrega tareas faltantes en proyectos existentes",
    )
    args = parser.parse_args()
    dry_run = args.dry_run
    append_missing = args.append_missing

    log_msg("=== INICIO DE CREACION DE ESTRUCTURA (FORZADO v2.1) ===")
    if dry_run:
        log_msg("MODO PRUEBA (DRY RUN): no se crean carpetas ni se renombra.")

    if not os.path.isdir(BASE_PROJECTS_DIR):
        log_msg(f"ERROR FATAL: No existe el directorio base: {BASE_PROJECTS_DIR}")
        sys.exit(1)

    folders_created = False
    base_depth = BASE_PROJECTS_DIR.count(os.sep)

    # Recorremos el directorio base
    for root, dirs, _ in os.walk(BASE_PROJECTS_DIR, topdown=True):
        # Limitar profundidad para no escanear todo el disco
        current_depth = root.count(os.sep) - base_depth
        if current_depth >= MAX_DEPTH:
            dirs[:] = []
            continue

        # Revisar cada carpeta encontrada
        for project_folder in list(dirs):
            project_path = os.path.join(root, project_folder)

            # Verificar si coincide con algun template (PMC, SATLINK, etc.)
            matched_template = None
            template_name = ""

            for key, template in STRUCTURE_TEMPLATES.items():
                if key.upper() in project_folder.upper():
                    matched_template = template
                    template_name = key
                    break

            if matched_template:
                log_msg(
                    f"Procesando Proyecto detectado: '{project_folder}' (Tipo: {template_name})"
                )

                # 1. Renombrar a MAYUSCULAS si es necesario
                project_folder_upper = project_folder.upper()
                project_path_upper = os.path.join(root, project_folder_upper)

                if project_folder != project_folder_upper:
                    if dry_run:
                        log_msg(f" -> DRY RUN: renombraria a: {project_folder_upper}")
                        project_path = project_path_upper
                    else:
                        try:
                            os.rename(project_path, project_path_upper)
                            log_msg(f" -> Renombrado a: {project_folder_upper}")
                            project_path = project_path_upper
                        except Exception as e:
                            log_msg(f" -> ERROR al renombrar: {e}")

                if (
                    template_name in SAFE_TEMPLATES
                    and has_existing_structure(project_path, template_name)
                    and not append_missing
                ):
                    log_msg(
                        f" -> ESTRUCTURA {template_name} EXISTENTE DETECTADA. OMITIENDO CREACION PARA EVITAR CAMBIOS."
                    )
                    dirs.remove(project_folder)
                    continue

                # 2. Crear estructura interna (SIN SALTAR SI YA EXISTE LA BASE)
                count_new = 0
                for subfolder in matched_template:
                    # Ruta completa de la subcarpeta
                    full_path = os.path.join(project_path, subfolder)

                    if not os.path.exists(full_path):
                        if dry_run:
                            log_msg(f" -> DRY RUN: crearia {subfolder}")
                            count_new += 1
                        else:
                            try:
                                os.makedirs(full_path, mode=0o775, exist_ok=True)
                                # Asegurar permisos
                                os.chmod(full_path, 0o775)
                                count_new += 1
                            except Exception as e:
                                log_msg(f" -> Error creando {subfolder}: {e}")

                if count_new > 0:
                    log_msg(
                        f" -> Se crearon {count_new} carpetas nuevas en este proyecto."
                    )
                    folders_created = True
                else:
                    log_msg(
                        " -> Estructura completa verificada (nada nuevo que crear)."
                    )

                # Sacamos la carpeta de la lista 'dirs' para no entrar recursivamente en ella en el os.walk principal
                dirs.remove(project_folder)

    should_scan = folders_created or append_missing
    if should_scan and not dry_run:
        if not folders_created:
            log_msg(
                "No se crearon carpetas nuevas, pero se ejecuta scanner por append-missing."
            )
        run_storage_scan()
    elif should_scan and dry_run:
        log_msg("MODO PRUEBA: no se ejecuta storage scan.")
    else:
        log_msg("No se requirieron cambios en ningun proyecto.")

    log_msg("=== FIN DEL PROCESO ===")
