#!/usr/bin/env python3
"""Resetea la BD de DEV: borra TODOS los datos (incluidos los que vinieron de
prod) y siembra datos de PRUEBA ficticios + crea sus carpetas en disco.

Pensado para correr DENTRO del contenedor (tiene backend + deps + la BD):
    docker exec terreneitor-app-dev python /app/ops/scripts/qa/seed_dev.py

NUNCA correr contra producción: detecta ENV y exige ENV!=production.
"""
import os
import sqlite3
import sys

# Seguridad: jamás sembrar/borrar en prod
if os.environ.get("ENV", "").lower() in {"prod", "production"}:
    print("ABORTADO: ENV es producción. Este script es solo para DEV.")
    sys.exit(1)

from backend.core import dependencias  # noqa: E402  (hash de contraseñas)

DB = os.environ.get("TERRENEITOR_DB_DIR", "/app/data/db") + "/terreneitor.db"
FILES = os.environ.get("BASE_FILES_DIR", "/app/data/files")
NOW = "2026-06-11T12:00:00"

USERS = [
    ("qa.dev@telconsulting.cl", "QA Admin", "QaDev2026!", "ADMIN"),
    ("qa.supervisor@telconsulting.cl", "QA Supervisor", "QaSup2026!", "SUPERVISOR"),
    ("qa.gerencia@telconsulting.cl", "QA Gerencia", "QaGer2026!", "GERENCIA"),
    ("qa.terreno@telconsulting.cl", "QA Terreno", "QaTerr2026!", "TERRENO"),
]
PROYECTOS = [
    (
        "INSTALACION_DOMICILIO_DEMO",
        "Movistar",
        "Santiago Centro",
        "Instalación de servicio (demo)",
    ),
    ("RETIRO_EQUIPOS_DEMO", "Entel", "Providencia", "Retiro de equipamiento (demo)"),
    ("TRASLADO_SERVICIO_DEMO", "WOM", "Maipú", "Traslado de servicio (demo)"),
    ("VISITA_PREVENTA_DEMO", "VTR", "Las Condes", "Visita técnica / preventa (demo)"),
]
CATS = ["Antes", "Durante", "Despues"]
ITEMS = ["Foto general", "Foto detalle", "Etiqueta/Serie"]
ESTADOS = [
    "ASIGNADA",
    "ASIGNADA",
    "COMPLETADA_TERRENO",
    "PENDIENTE_EXIF",
    "VALIDADA",
    "RECHAZADA",
]


def main():
    c = sqlite3.connect(DB)
    cur = c.cursor()
    for t in [
        "asignacion_usuarios",
        "asignaciones_plan",
        "planes_trabajo",
        "items",
        "categorias",
        "proyectos",
        "foto_descripciones",
        "foto_etiquetas",
        "reportes_historial",
        "report_jobs",
        "programacion_tareas",
        "ia_logs",
        "bridge_messages",
        "users",
    ]:
        try:
            cur.execute(f"delete from {t}")
        except sqlite3.OperationalError:
            pass
    cur.execute("delete from sqlite_sequence")

    uid = {}
    for em, nm, pw, rol in USERS:
        cur.execute(
            "insert into users (email,name,hashed_password,role,created_at) values (?,?,?,?,?)",
            (em, nm, dependencias.get_db_hash(pw), rol, NOW),
        )
        uid[rol] = cur.lastrowid

    item_ids = []
    for nombre, cli, area, desc in PROYECTOS:
        rb = f"{FILES}/{cli}/{area}/{nombre}"
        cur.execute(
            "insert into proyectos (nombre_pmc,cliente,area,ruta_base,estado_proyecto,created_at,descripcion_interna) values (?,?,?,?,?,?,?)",
            (nombre, cli, area, rb, "ACTIVO", NOW, desc),
        )
        pid = cur.lastrowid
        for cn in CATS:
            cur.execute(
                "insert into categorias (nombre,proyecto_id) values (?,?)", (cn, pid)
            )
            cid = cur.lastrowid
            for it in ITEMS:
                ri = f"{rb}/{cn}/{it}"
                cur.execute(
                    "insert into items (nombre,ruta_item,categoria_id) values (?,?,?)",
                    (it, ri, cid),
                )
                item_ids.append(cur.lastrowid)

    cur.execute(
        "insert into planes_trabajo (descripcion,fecha_creacion,estado_plan,fecha_inicio,fecha_fin) values (?,?,?,?,?)",
        ("Plan Demo Semana 24", NOW, "ABIERTO", "2026-06-09", "2026-06-15"),
    )
    plan = cur.lastrowid
    for i, it in enumerate(item_ids[:12]):
        est = ESTADOS[i % len(ESTADOS)]
        rech = "Foto borrosa, repetir" if est == "RECHAZADA" else None
        cur.execute(
            "insert into asignaciones_plan (plan_id,item_id,estado,fecha_asignacion,comentario_rechazo_supervisor,es_complementaria,usuario_id) values (?,?,?,?,?,?,?)",
            (plan, it, est, NOW, rech, 0, uid["TERRENO"]),
        )
        cur.execute(
            "insert into asignacion_usuarios (asignacion_id,usuario_id) values (?,?)",
            (cur.lastrowid, uid["TERRENO"]),
        )

    c.commit()

    # carpetas en disco (supervisor exige que exista ruta_base; terreno sube ahí)
    n = 0
    for (rb,) in c.execute(
        "select ruta_base from proyectos where ruta_base is not null"
    ):
        os.makedirs(rb, exist_ok=True)
        n += 1
    for (ri,) in c.execute("select ruta_item from items where ruta_item is not null"):
        os.makedirs(ri, exist_ok=True)
        n += 1
    c.close()
    print(
        f"Seed OK: {len(USERS)} usuarios, {len(PROYECTOS)} proyectos, {len(item_ids)} items, "
        f"12 asignaciones, {n} carpetas. Claves QA*: ver USERS en este script."
    )


if __name__ == "__main__":
    main()
