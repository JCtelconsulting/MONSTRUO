"""Migra la base de Terreneitor de SQLite al Postgres central de Monstruo.

Crea el schema `terreneitor` en la DB destino, crea las tablas desde los modelos
SQLAlchemy y copia los datos preservando IDs; al final ajusta las secuencias.
Idempotente a nivel de carga: si una tabla destino ya tiene filas, la salta
(usar --truncate para vaciarla y recargar).

Uso (dentro del contenedor, que ve a `db` por la red de monstruo-dev):
  python ops/scripts/migracion/sqlite_a_postgres.py \
    --sqlite /app/data/db/terreneitor.db \
    --pg "postgresql+psycopg2://USER:PASS@db:5432/monstruo_dev" \
    [--schema terreneitor] [--truncate]

NO toca la base SQLite (solo lectura). El destino NO debe ser produccion.
"""

import argparse
import os
import sys

from sqlalchemy import Integer, create_engine, insert, select, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.models.modelos import Base  # noqa: E402

# Orden de carga respetando claves foráneas.
ORDEN = [
    "users",
    "proyectos",
    "categorias",
    "items",
    "clientes",
    "planes_trabajo",
    "asignaciones_plan",
    "asignacion_usuarios",
    "reportes_historial",
    "report_jobs",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, help="ruta al .db de origen")
    ap.add_argument("--pg", required=True, help="URL postgresql+psycopg2 destino")
    ap.add_argument("--schema", default="terreneitor")
    ap.add_argument("--truncate", action="store_true", help="vaciar tablas destino")
    args = ap.parse_args()

    if "monstruo_dev" not in args.pg and os.environ.get("ENV") != "production":
        print(f"AVISO: destino no es monstruo_dev ({args.pg.split('@')[-1]})")

    src = create_engine(f"sqlite:///{args.sqlite}")
    # search_path al schema para que create_all/insert caigan ahí
    sep = "&" if "?" in args.pg else "?"
    dst = create_engine(
        f"{args.pg}{sep}options=-csearch_path%3D{args.schema},public",
        pool_pre_ping=True,
    )

    with dst.connect() as c:
        c.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{args.schema}"'))
        c.commit()
    Base.metadata.create_all(dst)
    print(f"[1/3] Schema '{args.schema}' + tablas listas en destino")

    tablas = {t.name: t for t in Base.metadata.sorted_tables}
    total = 0
    with src.connect() as s, dst.connect() as d:
        for nombre in ORDEN:
            t = tablas.get(nombre)
            if t is None:
                print(f"  - {nombre}: no está en los modelos, salto")
                continue
            existentes = d.execute(
                text(f'SELECT COUNT(*) FROM "{args.schema}".{nombre}')
            ).scalar()
            if existentes and args.truncate:
                d.execute(
                    text(f'TRUNCATE "{args.schema}".{nombre} RESTART IDENTITY CASCADE')
                )
                d.commit()
                existentes = 0
            if existentes:
                print(f"  - {nombre}: destino ya tiene {existentes} filas, salto")
                continue
            filas = [dict(r) for r in s.execute(select(t)).mappings().all()]
            if filas:
                d.execute(insert(t), filas)
                d.commit()
            print(f"  + {nombre}: {len(filas)} filas")
            total += len(filas)
    print(f"[2/3] Datos copiados: {total} filas")

    # Secuencias: dejarlas después del max(id) de cada tabla con id autoincremental
    with dst.connect() as d:
        for nombre in ORDEN:
            t = tablas.get(nombre)
            # solo ids enteros autoincrementales (report_jobs usa id de texto)
            if t is None or "id" not in t.c or not isinstance(t.c.id.type, Integer):
                continue
            d.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{args.schema}.{nombre}', 'id'), "
                    f'COALESCE((SELECT MAX(id) FROM "{args.schema}".{nombre}), 1))'
                )
            )
        d.commit()
    print("[3/3] Secuencias ajustadas")

    # Verificación rápida origen vs destino
    insp_ok = True
    with src.connect() as s, dst.connect() as d:
        for nombre in ORDEN:
            if nombre not in tablas:
                continue
            a = s.execute(text(f"SELECT COUNT(*) FROM {nombre}")).scalar()
            b = d.execute(
                text(f'SELECT COUNT(*) FROM "{args.schema}".{nombre}')
            ).scalar()
            marca = "OK " if a == b else "DIF"
            if a != b:
                insp_ok = False
            print(f"  [{marca}] {nombre}: sqlite={a} pg={b}")
    print("RESULTADO:", "PASS" if insp_ok else "FAIL")
    return 0 if insp_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
