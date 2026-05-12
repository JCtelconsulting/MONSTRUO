"""Importa la planificación anual oficial desde los docx a la DB.

Lee los 5 archivos en fundacion/data/planificaciones/ y vuelca:
- Actividades únicas → fundacion.actividades (+ competencias asociadas)
- Días planificados → fundacion.planificacion_dia (+ bloques + competencias)

Es idempotente: si encuentra una actividad por (nombre + tipo + subtipo) ya
existente, la actualiza. Si encuentra un (nivel, fecha) ya planificado, lo
sobrescribe (delete + insert).

Uso típico:
    docker run --rm \\
        --network monstruo-dev_default \\
        -v /srv/monstruo_dev/fundacion/data/planificaciones:/data:ro \\
        -v /srv/monstruo_dev/fundacion/scripts/import_planificacion.py:/import.py:ro \\
        -e DB_HOST=db -e DB_USER=monstruo -e DB_PASS=monstruo -e DB_NAME=monstruo_dev \\
        python:3.12-slim bash -c "pip install --quiet python-docx psycopg && python /import.py"
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Optional

import psycopg
from docx import Document

# ── Configuración ──────────────────────────────────────────────────────

BASE = Path(os.environ.get("DATA_DIR", "/data"))

ARCHIVOS = [
    # (nivel_codigo, doc_label, ruta relativa, año por defecto)
    ("prekinder_kinder", "Prekinder-Kinder 2026",
     "Prekinder y Kinder/2026Planificación Prekinder y Kinder.docx", 2026),
    ("1ro_2do",          "1ro-2do (1er sem 2026)",
     "1ro y 2do básico/1er Semestre 1ro y 2do Básico.docx", 2026),
    ("1ro_2do",          "1ro-2do (2do sem 2026)",
     "1ro y 2do básico/2° semestre 1°y 2° 2026.docx", 2026),
    ("3ro_4to",          "3ro-4to (1er sem 2026)",
     "3ro y 4to básico/1er semestre 3°y 4° 2026.docx", 2026),
    ("3ro_4to",          "3ro-4to (anual 2025)",
     "3ro y 4to básico/Anual-Planificación 3°y 4° 2025.docx", 2025),
]

MESES_ES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

BLOQUE_NORMALIZADO = {
    "JUEGOS PARA CRECER": "juegos_para_crecer",
    "TALLER SOCIOEMOCIONAL": "taller_socioemocional",
    "GLIFING": "glifing",
    "COLACIÓN": "colacion",
    "COLACION": "colacion",
    "JUEGO LIBRE": "juego_libre",
    "VIERNES DE COMUNIDAD": "viernes_comunidad",
    "PICHINTÚN": "pichintun",
    "PICHINTUN": "pichintun",
}

SUBTIPO_NORMALIZADO = {
    "psicomotor": "psicomotor",
    "sensorial": "sensorial",
    "cognitivo": "cognitivo",
    "afectivo": "afectivo",
    "artistico": "artistico",
    "artístico": "artistico",
    "adaptativo": "adaptativo",
}

RE_DIA = re.compile(
    r"D[ÍI]A\s+(\d+)[\s:\-]+(LUNES|MARTES|MIÉRCOLES|MIERCOLES|JUEVES|VIERNES)\s+(\d+)\s+DE\s+([A-ZÁÉÍÓÚÑa-záéíóúñ]+)",
    re.IGNORECASE,
)
RE_BLOQUE = re.compile(
    r"(JUEGOS PARA CRECER|TALLER SOCIOEMOCIONAL|GLIFING|COLACI[ÓO]N|JUEGO LIBRE|PICHINT[ÚU]N|VIERNES DE COMUNIDAD)\s*\(?([a-záéíóú]+)?\)?",
    re.IGNORECASE,
)
RE_COMP = re.compile(r"\b(AC|AG|CS|HR|RD)(\d)\b")


def normalize(s: str) -> str:
    """lowercase + sin acentos para el nombre_normalizado."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def texto_tabla(t):
    out = []
    for row in t.rows:
        cells = [c.text.strip() for c in row.cells if c.text.strip()]
        if cells:
            out.append(cells)
    return out


def parsear_dia(month_word: str, day_num: int, year: int) -> Optional[date]:
    mes_num = MESES_ES.get(month_word.upper())
    if not mes_num:
        return None
    try:
        return date(year, mes_num, day_num)
    except ValueError:
        return None


def procesar_docx(path: Path):
    """Retorna lista de días con bloques estructurados."""
    doc = Document(str(path))
    dias = []
    dia_actual = None

    for t in doc.tables:
        rows = texto_tabla(t)
        flat = " | ".join(" || ".join(r) for r in rows)

        md = RE_DIA.search(flat)
        if md:
            num = int(md.group(1))
            if not dia_actual or dia_actual["num"] != num:
                dia_actual = {
                    "num": num,
                    "dow": md.group(2).upper(),
                    "dia_mes": int(md.group(3)),
                    "mes": md.group(4).upper(),
                    "bloques": [],
                }
                dias.append(dia_actual)
            continue

        if not dia_actual:
            continue

        mb = RE_BLOQUE.search(flat)
        if not mb:
            continue
        bloque_palabra = mb.group(1).upper().strip()
        bloque_codigo = BLOQUE_NORMALIZADO.get(bloque_palabra)
        if not bloque_codigo:
            continue
        subtipo_palabra = (mb.group(2) or "").lower().strip()
        subtipo_codigo = SUBTIPO_NORMALIZADO.get(subtipo_palabra)

        comps = sorted({f"{a}{n}" for a, n in RE_COMP.findall(flat)})

        nombre = None
        for r in rows:
            joined = " ".join(r).upper()
            if "NOMBRE DE LA ACTIVIDAD" in joined or "NOMBRE DEL JUEGO" in joined:
                for cell in r:
                    cu = cell.upper()
                    if "NOMBRE DE LA ACTIVIDAD" in cu or "NOMBRE DEL JUEGO" in cu:
                        continue
                    if cell.strip() and len(cell) < 120:
                        nombre = cell.strip()
                        break
                if nombre:
                    break

        materiales = None
        for r in rows:
            for c in r:
                if c.lower().startswith("materiales"):
                    materiales = c[len("materiales"):].strip(":").strip()
                    break
            if materiales:
                break

        resultado = None
        for r in rows:
            for cell in r:
                if cell.upper().startswith("RESULTADO DE APRENDIZAJE"):
                    continue
            for i, cell in enumerate(r):
                if "RESULTADO DE APRENDIZAJE" in cell.upper():
                    # buscar el siguiente cell con contenido sustancial
                    for c2 in r:
                        if "RESULTADO DE APRENDIZAJE" in c2.upper():
                            continue
                        if c2.strip() and len(c2) > 20:
                            resultado = c2.strip()
                            break
                    break
            if resultado:
                break

        dia_actual["bloques"].append({
            "bloque_codigo": bloque_codigo,
            "subtipo_codigo": subtipo_codigo,
            "nombre": nombre,
            "competencias": comps,
            "resultado": resultado,
            "materiales": materiales,
        })

    return dias


def main():
    if not BASE.exists():
        print(f"ERROR: no existe {BASE}", file=sys.stderr)
        return 1

    db_host = os.environ.get("DB_HOST", "db")
    db_user = os.environ.get("DB_USER", "monstruo")
    db_pass = os.environ.get("DB_PASS", "monstruo")
    db_name = os.environ.get("DB_NAME", "monstruo_dev")
    conn_str = f"host={db_host} user={db_user} password={db_pass} dbname={db_name}"

    print(f"== Conectando a {db_host}/{db_name} ==")
    conn = psycopg.connect(conn_str, autocommit=False)

    with conn.cursor() as cur:
        # Catálogos lookup
        cur.execute("SELECT codigo, id FROM fundacion.niveles")
        niveles = dict(cur.fetchall())
        cur.execute("SELECT codigo, id FROM fundacion.bloque_tipos")
        tipos = dict(cur.fetchall())
        cur.execute("SELECT codigo, id, bloque_tipo_id FROM fundacion.bloque_subtipos")
        subtipos = {(row[2], row[0]): row[1] for row in cur.fetchall()}
        cur.execute("SELECT codigo, id FROM fundacion.competencias")
        comps = dict(cur.fetchall())

    print(f"  niveles={list(niveles)} tipos={list(tipos)} comps={len(comps)}")

    actividades_creadas = 0
    actividades_actualizadas = 0
    planif_dias_creados = 0
    planif_bloques_creados = 0
    planif_comp_link = 0
    actcomp_link = 0
    actividades_por_clave: dict[tuple, int] = {}

    for nivel_codigo, label, rel, year in ARCHIVOS:
        path = BASE / rel
        if not path.exists():
            print(f"  ⚠ no existe: {rel}")
            continue
        nivel_id = niveles.get(nivel_codigo)
        if not nivel_id:
            print(f"  ⚠ nivel desconocido: {nivel_codigo}")
            continue

        print(f"\n== {label} ==")
        try:
            dias = procesar_docx(path)
        except Exception as e:
            print(f"  ERROR procesando: {e}")
            continue
        print(f"  días detectados: {len(dias)}")

        with conn.cursor() as cur:
            for d in dias:
                fecha = parsear_dia(d["mes"], d["dia_mes"], year)
                if not fecha:
                    continue

                # Upsert día (delete bloques previos)
                cur.execute(
                    """
                    INSERT INTO fundacion.planificacion_dia (nivel_id, fecha, numero_dia, dia_semana, fuente_doc)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (nivel_id, fecha) DO UPDATE SET
                        numero_dia = EXCLUDED.numero_dia,
                        dia_semana = EXCLUDED.dia_semana,
                        fuente_doc = EXCLUDED.fuente_doc
                    RETURNING id, (xmax = 0) AS inserted
                    """,
                    (nivel_id, fecha, d["num"], d["dow"], label),
                )
                row = cur.fetchone()
                dia_id, inserted = row[0], row[1]
                if inserted:
                    planif_dias_creados += 1

                cur.execute(
                    "DELETE FROM fundacion.planificacion_bloque WHERE planificacion_dia_id = %s",
                    (dia_id,),
                )

                for orden, b in enumerate(d["bloques"], start=1):
                    tipo_id = tipos.get(b["bloque_codigo"])
                    if not tipo_id:
                        continue
                    subtipo_id = subtipos.get((tipo_id, b["subtipo_codigo"])) if b["subtipo_codigo"] else None

                    # Upsert actividad (si tiene nombre)
                    actividad_id = None
                    if b["nombre"]:
                        clave = (normalize(b["nombre"]), tipo_id, subtipo_id or -1)
                        if clave in actividades_por_clave:
                            actividad_id = actividades_por_clave[clave]
                            cur.execute(
                                """
                                UPDATE fundacion.actividades
                                   SET veces_referenciada = veces_referenciada + 1,
                                       resultado_aprendizaje = COALESCE(NULLIF(%s, ''), resultado_aprendizaje),
                                       materiales_tipicos = COALESCE(NULLIF(%s, ''), materiales_tipicos)
                                 WHERE id = %s
                                """,
                                (b["resultado"] or "", (b["materiales"] or "")[:1000], actividad_id),
                            )
                            actividades_actualizadas += 1
                        else:
                            cur.execute(
                                """
                                INSERT INTO fundacion.actividades
                                  (nombre, nombre_normalizado, bloque_tipo_id, bloque_subtipo_id,
                                   resultado_aprendizaje, materiales_tipicos, fuente_doc, veces_referenciada)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                                ON CONFLICT (nombre_normalizado, bloque_tipo_id, COALESCE(bloque_subtipo_id, -1))
                                DO UPDATE SET veces_referenciada = fundacion.actividades.veces_referenciada + 1
                                RETURNING id
                                """,
                                (b["nombre"], normalize(b["nombre"]), tipo_id, subtipo_id,
                                 b["resultado"], (b["materiales"] or "")[:1000], label),
                            )
                            actividad_id = cur.fetchone()[0]
                            actividades_por_clave[clave] = actividad_id
                            actividades_creadas += 1

                        # Vincular competencias a la actividad
                        for cc in b["competencias"]:
                            comp_id = comps.get(cc)
                            if not comp_id:
                                continue
                            cur.execute(
                                """
                                INSERT INTO fundacion.actividad_competencias (actividad_id, competencia_id)
                                VALUES (%s, %s)
                                ON CONFLICT DO NOTHING
                                """,
                                (actividad_id, comp_id),
                            )
                            if cur.rowcount > 0:
                                actcomp_link += 1

                    # Insertar bloque planificado
                    cur.execute(
                        """
                        INSERT INTO fundacion.planificacion_bloque
                          (planificacion_dia_id, orden, bloque_tipo_id, bloque_subtipo_id,
                           actividad_id, nombre_actividad, resultado_aprendizaje,
                           materiales_sugeridos)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (dia_id, orden, tipo_id, subtipo_id, actividad_id,
                         b["nombre"], b["resultado"], (b["materiales"] or "")[:1000]),
                    )
                    bloque_id = cur.fetchone()[0]
                    planif_bloques_creados += 1

                    # Vincular competencias al bloque planificado
                    for cc in b["competencias"]:
                        comp_id = comps.get(cc)
                        if not comp_id:
                            continue
                        cur.execute(
                            """
                            INSERT INTO fundacion.planificacion_bloque_competencias
                              (planificacion_bloque_id, competencia_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (bloque_id, comp_id),
                        )
                        if cur.rowcount > 0:
                            planif_comp_link += 1

        conn.commit()
        print(f"  ✓ {label} confirmado")

    print()
    print("== RESUMEN ==")
    print(f"  Actividades creadas:       {actividades_creadas}")
    print(f"  Actividades referenciadas: {actividades_actualizadas}")
    print(f"  Días planificados nuevos:  {planif_dias_creados}")
    print(f"  Bloques planificados:      {planif_bloques_creados}")
    print(f"  Links actividad↔competencia: {actcomp_link}")
    print(f"  Links bloque↔competencia:    {planif_comp_link}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
