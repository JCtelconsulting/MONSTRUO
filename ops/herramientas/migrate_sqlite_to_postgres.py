#!/usr/bin/env python3
import os
import re
import sqlite3
import sys
from typing import List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CODE_ROOT = os.path.join(PROJECT_ROOT, "code")
if CODE_ROOT not in sys.path:
    sys.path.insert(0, CODE_ROOT)

from app.core import db

DEFAULT_SQLITE_PATH = os.path.join(PROJECT_ROOT, "data", "db", "monstruo.db")

SQLITE_PATH = os.getenv("SQLITE_PATH", DEFAULT_SQLITE_PATH)

def _convert_sql_for_postgres(sql: str) -> str:
    sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "SERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY", "SERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"BOOLEAN\s+DEFAULT\s+1", "BOOLEAN DEFAULT TRUE", sql, flags=re.I)
    sql = re.sub(r"BOOLEAN\s+DEFAULT\s+0", "BOOLEAN DEFAULT FALSE", sql, flags=re.I)
    return sql

def _strip_foreign_keys(sql: str) -> str:
    lines = sql.splitlines()
    kept = []
    for line in lines:
        if "FOREIGN KEY" in line.upper() or "REFERENCES" in line.upper():
            continue
        kept.append(line)
    cleaned = "\n".join(kept)
    cleaned = re.sub(r",\s*\)\s*$", "\n)", cleaned, flags=re.M)
    cleaned = re.sub(r",\s*\n\)", "\n)", cleaned, flags=re.M)
    return cleaned

def _qname(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

def _get_sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _list_sqlite_tables(conn: sqlite3.Connection) -> List[Tuple[str, str]]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [(r["name"], r["sql"]) for r in rows]

def _sqlite_column_types(conn: sqlite3.Connection, table: str) -> dict:
    rows = conn.execute(f"PRAGMA table_info({_qname(table)})").fetchall()
    return {r[1]: (r[2] or "").upper() for r in rows}

def _pg_table_exists(pg_conn, table: str) -> bool:
    row = pg_conn.execute("SELECT to_regclass(?) AS t", (table,)).fetchone()
    return bool(row and row.get("t"))

def _truncate_table(pg_conn, table: str) -> None:
    if not _pg_table_exists(pg_conn, table):
        return
    pg_conn.execute(f"TRUNCATE TABLE {_qname(table)} RESTART IDENTITY CASCADE")

def main() -> int:
    if not db.is_postgres():
        print("ERROR: DB_URL debe apuntar a PostgreSQL para ejecutar la migracion.")
        return 1

    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: SQLite DB no encontrada en {SQLITE_PATH}")
        return 1

    sqlite_conn = _get_sqlite_conn()
    pg_conn = db.get_conn()

    try:
        tables = _list_sqlite_tables(sqlite_conn)
        if not tables:
            print("No se encontraron tablas en SQLite.")
            return 1

        # Crear tablas faltantes en Postgres usando el SQL de SQLite (resolviendo dependencias)
        pending = [(t, s) for t, s in tables if s]
        created_in_pass = True
        while pending and created_in_pass:
            created_in_pass = False
            next_pending = []
            for table, create_sql in pending:
                if _pg_table_exists(pg_conn, table):
                    continue
                pg_sql = _convert_sql_for_postgres(create_sql)
                try:
                    pg_conn.execute(pg_sql)
                    created_in_pass = True
                except Exception as e:
                    try:
                        pg_conn.rollback()
                    except Exception:
                        pass
                    msg = str(e)
                    if "does not exist" in msg or "undefined_table" in msg:
                        next_pending.append((table, create_sql))
                    else:
                        raise
            pg_conn.commit()
            pending = next_pending

        if pending:
            # Crear tablas restantes sin restricciones FK para evitar bloqueos por dependencias
            for table, create_sql in pending:
                if _pg_table_exists(pg_conn, table):
                    continue
                pg_sql = _convert_sql_for_postgres(_strip_foreign_keys(create_sql))
                pg_conn.execute(pg_sql)
            pg_conn.commit()

        # Limpiar tablas destino para migracion limpia
        for table, _ in tables:
            _truncate_table(pg_conn, table)
        pg_conn.commit()

        # Migrar datos
        try:
            pg_conn.execute("SET session_replication_role = replica")
            pg_conn.commit()
        except Exception:
            pass

        bool_columns = {
            "customers": {"is_active"},
            "products": {"is_service"},
        }

        for table, _ in tables:
            rows = sqlite_conn.execute(f"SELECT * FROM {_qname(table)}").fetchall()
            if not rows:
                continue

            columns = rows[0].keys()
            col_types = _sqlite_column_types(sqlite_conn, table)
            cols_sql = ", ".join(_qname(c) for c in columns)
            placeholders = ", ".join("?" for _ in columns)
            insert_sql = f"INSERT INTO {_qname(table)} ({cols_sql}) VALUES ({placeholders})"

            for row in rows:
                values = []
                for col in columns:
                    val = row[col]
                    if table in bool_columns and col in bool_columns[table]:
                        if val is None:
                            values.append(None)
                        else:
                            values.append(bool(int(val)))
                    else:
                        values.append(val)
                pg_conn.execute(insert_sql, tuple(values))

            # Actualizar secuencia si existe columna id
            if "id" in columns and "INT" in (col_types.get("id") or ""):
                max_id_row = sqlite_conn.execute(f"SELECT MAX(id) AS m FROM {_qname(table)}").fetchone()
                max_id = max_id_row["m"] if max_id_row and max_id_row["m"] is not None else 0
                pg_conn.execute(
                    "SELECT setval(pg_get_serial_sequence(?, ?), ?, true)",
                    (table, "id", max_id)
                )

        pg_conn.commit()
        try:
            pg_conn.execute("SET session_replication_role = origin")
            pg_conn.commit()
        except Exception:
            pass
        print("MIGRACION_OK")
        return 0
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
