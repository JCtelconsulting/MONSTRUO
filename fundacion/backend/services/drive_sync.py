"""Sincronización de planillas Google Sheets → DB de Fundación.

Cada sede tiene una planilla con hojas "Matriculas" y "Asistencia". Este
servicio las lee con la cuenta de servicio configurada en
FUNDACION_DRIVE_SA_PATH y vuelca los datos a la DB.

Reglas:
- La planilla es la fuente de verdad. Lo que esté en la DB y no en la planilla
  se marca presente_en_planilla=FALSE (no se borra, para no perder histórico).
- La identidad del alumno es (sede_id, rut_normalizado).
- Cada sede sincroniza en su propia transacción: si una falla, las otras siguen.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

import gspread
from google.oauth2.service_account import Credentials

from plataforma.core import db

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

CODIGOS_VALIDOS = {"P", "A", "AJ", "F/V", "ST", "NM", "FLEX"}

# Índices 0-based de columnas en la hoja Matriculas
MAT_COL_CORRELATIVO = 1
MAT_COL_NOMBRE = 2
MAT_COL_RUT = 3
MAT_COL_FECHA_NAC = 4
MAT_COL_EDAD = 5
MAT_COL_NACIONALIDAD = 6
MAT_COL_TIENE_NEE = 7
MAT_COL_NEE_DETALLE = 8
MAT_COL_SEXO = 9
MAT_COL_CURSO_COLEGIO = 10
MAT_COL_CURSO_AFTER = 11
MAT_COL_PLAN = 12
MAT_COL_DIAS_FLEX = 13
MAT_COL_GESTORA = 14
MAT_COL_ANOS_AFTER = 15
MAT_COL_ESTADO_ALUMNO = 16
MAT_COL_CUIDADOR_NOMBRE = 17
MAT_COL_CUIDADOR_RUT = 18
MAT_COL_CUIDADOR_FECHA_NAC = 19
MAT_COL_CUIDADOR_EDAD = 20
MAT_COL_CUIDADOR_NACIONALIDAD = 21
MAT_COL_CUIDADOR_SEXO = 22
MAT_COL_CUIDADOR_TELEFONO = 23
MAT_COL_GRUPO_FAMILIAR = 24
MAT_COL_ESTADO_MATRICULA = 25
MAT_COL_FECHA_MATRICULACION = 26
# col 27 = Sede en planilla; no la guardamos, ya está en sede_id
MAT_COL_REUNION = 28
MAT_COL_FORMULARIO = 29
MAT_COL_ENTREVISTA = 30
MAT_COL_DOCUMENTOS = 31
MAT_COL_INICIO_PARTICIPACION = 32
MAT_COL_INICIO_ADAPTACION = 33
MAT_COL_EVAL_ADAPTACION = 34
MAT_COL_ASISTENCIA_REGULAR = 35
MAT_COL_RIESGO_DESERCION = 36
MAT_COL_FECHA_DESERCION = 37
MAT_COL_MOTIVO_DESERCION = 38
MAT_COL_ANO_INGRESO = 39
MAT_COL_MES_INGRESO = 40
MAT_COL_MES_MATRICULA = 41
MAT_COL_MES_DESERCION = 42
MAT_COL_MATRICULA_ACTIVA = 43

MAT_DATA_START = 3  # fila 4 visualmente: headers están en fila 3 (idx 2)

ASI_HEADER_ROW = 6   # fila 7 visualmente: cabeceras con fechas
ASI_DATA_START = 7   # fila 8 visualmente
ASI_FECHA_COL_START = 2  # col 3 visualmente


@dataclass
class SedeSyncResult:
    sede_id: int
    sede_code: str
    status: str = "running"
    alumnos_creados: int = 0
    alumnos_actualizados: int = 0
    alumnos_desaparecidos: int = 0
    asistencias_insertadas: int = 0
    asistencias_actualizadas: int = 0
    codigos_desconocidos: int = 0
    error: Optional[str] = None


# ── Helpers de parseo ───────────────────────────────────────────────────────

def _norm_rut(rut: str) -> str:
    if not rut:
        return ""
    return "".join(c for c in str(rut).lower() if c.isalnum())


def _bool_si_no(val: Any) -> Optional[bool]:
    if val is None:
        return None
    v = str(val).strip().lower()
    if v in ("si", "sí", "1", "true", "yes", "verdadero"):
        return True
    if v in ("no", "0", "false", "falso"):
        return False
    return None


def _int(val: Any) -> Optional[int]:
    if val is None or str(val).strip() == "":
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def _date(val: Any) -> Optional[date]:
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _cell(row: list, idx: int) -> str:
    if idx < len(row) and row[idx] is not None:
        return str(row[idx]).strip()
    return ""


# ── Acceso a Google Sheets ──────────────────────────────────────────────────

def _get_gspread_client():
    sa_path = os.environ.get(
        "FUNDACION_DRIVE_SA_PATH",
        "/run/secrets/monstruo-fundacion-drive.json",
    )
    creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    return gspread.authorize(creds)


# ── Parseo ──────────────────────────────────────────────────────────────────

def parse_matriculas(rows: list[list[str]]) -> list[dict]:
    out: list[dict] = []
    for r in rows[MAT_DATA_START:]:
        correlativo = _int(_cell(r, MAT_COL_CORRELATIVO))
        nombre = _cell(r, MAT_COL_NOMBRE)
        if not nombre or correlativo is None:
            continue
        rut_raw = _cell(r, MAT_COL_RUT)
        out.append({
            "correlativo": correlativo,
            "nombre_completo": nombre,
            "rut": rut_raw or None,
            "rut_normalizado": _norm_rut(rut_raw) or None,
            "fecha_nacimiento": _date(_cell(r, MAT_COL_FECHA_NAC)),
            "edad": _int(_cell(r, MAT_COL_EDAD)),
            "nacionalidad": _cell(r, MAT_COL_NACIONALIDAD) or None,
            "tiene_nee": _bool_si_no(_cell(r, MAT_COL_TIENE_NEE)),
            "nee_detalle": _cell(r, MAT_COL_NEE_DETALLE) or None,
            "sexo": _cell(r, MAT_COL_SEXO) or None,
            "curso_colegio": _cell(r, MAT_COL_CURSO_COLEGIO) or None,
            "curso_after": _cell(r, MAT_COL_CURSO_AFTER) or None,
            "plan": _cell(r, MAT_COL_PLAN) or None,
            "dias_flex_por_semana": _int(_cell(r, MAT_COL_DIAS_FLEX)),
            "gestora_a_cargo": _cell(r, MAT_COL_GESTORA) or None,
            "anos_en_after": _cell(r, MAT_COL_ANOS_AFTER) or None,
            "estado_alumno": _cell(r, MAT_COL_ESTADO_ALUMNO) or None,
            "cuidador_nombre": _cell(r, MAT_COL_CUIDADOR_NOMBRE) or None,
            "cuidador_rut": _cell(r, MAT_COL_CUIDADOR_RUT) or None,
            "cuidador_fecha_nacimiento": _date(_cell(r, MAT_COL_CUIDADOR_FECHA_NAC)),
            "cuidador_edad": _int(_cell(r, MAT_COL_CUIDADOR_EDAD)),
            "cuidador_nacionalidad": _cell(r, MAT_COL_CUIDADOR_NACIONALIDAD) or None,
            "cuidador_sexo": _cell(r, MAT_COL_CUIDADOR_SEXO) or None,
            "cuidador_telefono": _cell(r, MAT_COL_CUIDADOR_TELEFONO) or None,
            "grupo_familiar": _int(_cell(r, MAT_COL_GRUPO_FAMILIAR)),
            "estado_matricula": _cell(r, MAT_COL_ESTADO_MATRICULA) or None,
            "fecha_matriculacion": _cell(r, MAT_COL_FECHA_MATRICULACION) or None,
            "reunion_informativa": _bool_si_no(_cell(r, MAT_COL_REUNION)),
            "formulario_postulacion": _bool_si_no(_cell(r, MAT_COL_FORMULARIO)),
            "entrevista_psicosocial": _cell(r, MAT_COL_ENTREVISTA) or None,
            "documentos_firmados": _bool_si_no(_cell(r, MAT_COL_DOCUMENTOS)),
            "fecha_inicio_participacion": _date(_cell(r, MAT_COL_INICIO_PARTICIPACION)),
            "fecha_inicio_adaptacion": _date(_cell(r, MAT_COL_INICIO_ADAPTACION)),
            "evaluacion_adaptacion": _cell(r, MAT_COL_EVAL_ADAPTACION) or None,
            "asistencia_regular": _bool_si_no(_cell(r, MAT_COL_ASISTENCIA_REGULAR)),
            "riesgo_desercion": _bool_si_no(_cell(r, MAT_COL_RIESGO_DESERCION)),
            "fecha_desercion": _date(_cell(r, MAT_COL_FECHA_DESERCION)),
            "motivo_desercion": _cell(r, MAT_COL_MOTIVO_DESERCION) or None,
            "ano_ingreso_after": _int(_cell(r, MAT_COL_ANO_INGRESO)),
            "mes_ingreso_after": _int(_cell(r, MAT_COL_MES_INGRESO)),
            "mes_matricula": _int(_cell(r, MAT_COL_MES_MATRICULA)),
            "mes_desercion": _int(_cell(r, MAT_COL_MES_DESERCION)),
            "matricula_activa": _bool_si_no(_cell(r, MAT_COL_MATRICULA_ACTIVA)),
        })
    return out


def parse_asistencia(rows: list[list[str]]) -> list[dict]:
    """Devuelve filas {correlativo, nombre, codigos: {fecha: codigo}}."""
    if len(rows) <= ASI_HEADER_ROW:
        return []

    header = rows[ASI_HEADER_ROW]
    fechas: list[Optional[date]] = []
    for cell in header[ASI_FECHA_COL_START:]:
        fechas.append(_date(cell))

    alumnos: list[dict] = []
    for r in rows[ASI_DATA_START:]:
        correlativo = _int(_cell(r, 0))
        nombre = _cell(r, 1)
        if not nombre or correlativo is None:
            continue
        codigos: dict[date, str] = {}
        for j, fecha in enumerate(fechas):
            if fecha is None:
                continue
            col_idx = ASI_FECHA_COL_START + j
            val = _cell(r, col_idx)
            if not val:
                continue
            codigos[fecha] = val
        alumnos.append({
            "correlativo": correlativo,
            "nombre_completo": nombre,
            "codigos": codigos,
        })
    return alumnos


# ── Upserts en DB ───────────────────────────────────────────────────────────

ALUMNO_COLS = [
    "correlativo", "nombre_completo", "rut", "rut_normalizado",
    "fecha_nacimiento", "edad", "nacionalidad", "tiene_nee", "nee_detalle",
    "sexo", "curso_colegio", "curso_after", "plan", "dias_flex_por_semana",
    "gestora_a_cargo", "anos_en_after", "estado_alumno",
    "cuidador_nombre", "cuidador_rut", "cuidador_fecha_nacimiento",
    "cuidador_edad", "cuidador_nacionalidad", "cuidador_sexo",
    "cuidador_telefono", "grupo_familiar",
    "estado_matricula", "fecha_matriculacion", "reunion_informativa",
    "formulario_postulacion", "entrevista_psicosocial", "documentos_firmados",
    "fecha_inicio_participacion", "fecha_inicio_adaptacion",
    "evaluacion_adaptacion", "asistencia_regular", "riesgo_desercion",
    "fecha_desercion", "motivo_desercion",
    "ano_ingreso_after", "mes_ingreso_after", "mes_matricula", "mes_desercion",
    "matricula_activa",
]


def upsert_alumnos(conn, sede_id: int, alumnos_data: list[dict]) -> tuple[int, int, dict[int, int]]:
    """Inserta o actualiza alumnos. Devuelve (creados, actualizados, correlativo→alumno_id)."""
    creados, actualizados = 0, 0
    correlativo_to_id: dict[int, int] = {}

    for a in alumnos_data:
        if not a.get("rut_normalizado"):
            logger.warning(
                "Alumno sin RUT en sede %s: %s (correlativo %s) — saltado",
                sede_id, a.get("nombre_completo"), a.get("correlativo"),
            )
            continue

        row = conn.execute(
            "SELECT id FROM fundacion.alumnos WHERE sede_id = %s AND rut_normalizado = %s",
            (sede_id, a["rut_normalizado"]),
        ).fetchone()

        values = tuple(a[c] for c in ALUMNO_COLS)

        if row:
            alumno_id = row["id"]
            set_clause = ", ".join(f"{c} = %s" for c in ALUMNO_COLS)
            conn.execute(
                f"""
                UPDATE fundacion.alumnos
                SET {set_clause},
                    synced_at = CURRENT_TIMESTAMP,
                    presente_en_planilla = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                values + (alumno_id,),
            )
            actualizados += 1
        else:
            placeholders = ", ".join(["%s"] * (len(ALUMNO_COLS) + 1))
            cur = conn.execute(
                f"""
                INSERT INTO fundacion.alumnos (sede_id, {", ".join(ALUMNO_COLS)})
                VALUES ({placeholders})
                RETURNING id
                """,
                (sede_id,) + values,
            )
            alumno_id = cur.fetchone()["id"]
            creados += 1

        correlativo_to_id[a["correlativo"]] = alumno_id

    return creados, actualizados, correlativo_to_id


def marcar_desaparecidos(conn, sede_id: int, ruts_vistos: set[str]) -> int:
    if not ruts_vistos:
        cur = conn.execute(
            """
            UPDATE fundacion.alumnos
            SET presente_en_planilla = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE sede_id = %s AND presente_en_planilla = TRUE
            RETURNING id
            """,
            (sede_id,),
        )
        return len(cur.fetchall())

    placeholders = ", ".join(["%s"] * len(ruts_vistos))
    cur = conn.execute(
        f"""
        UPDATE fundacion.alumnos
        SET presente_en_planilla = FALSE, updated_at = CURRENT_TIMESTAMP
        WHERE sede_id = %s
          AND rut_normalizado NOT IN ({placeholders})
          AND presente_en_planilla = TRUE
        RETURNING id
        """,
        (sede_id, *ruts_vistos),
    )
    return len(cur.fetchall())


def upsert_asistencia(
    conn, sede_id: int, correlativo_to_id: dict[int, int], asistencia_data: list[dict]
) -> tuple[int, int, int]:
    insertadas, actualizadas, desconocidos = 0, 0, 0

    for row in asistencia_data:
        alumno_id = correlativo_to_id.get(row["correlativo"])
        if not alumno_id:
            continue
        for fecha, codigo in row["codigos"].items():
            codigo_conocido = codigo in CODIGOS_VALIDOS
            if not codigo_conocido:
                desconocidos += 1
            cur = conn.execute(
                """
                INSERT INTO fundacion.asistencia_diaria
                    (alumno_id, sede_id, fecha, codigo, codigo_conocido)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (alumno_id, fecha) DO UPDATE SET
                    codigo = EXCLUDED.codigo,
                    codigo_conocido = EXCLUDED.codigo_conocido,
                    synced_at = CURRENT_TIMESTAMP
                RETURNING (xmax = 0) AS inserted
                """,
                (alumno_id, sede_id, fecha, codigo, codigo_conocido),
            )
            if cur.fetchone()["inserted"]:
                insertadas += 1
            else:
                actualizadas += 1

    return insertadas, actualizadas, desconocidos


# ── Sync ────────────────────────────────────────────────────────────────────

def sync_sede(sede_id: int, gc=None) -> SedeSyncResult:
    """Sincroniza una sede. Cada sede en su propia transacción."""
    conn = db.get_conn()
    try:
        sede = conn.execute(
            "SELECT id, code, drive_spreadsheet_id FROM fundacion.sedes WHERE id = %s",
            (sede_id,),
        ).fetchone()
        if not sede:
            return SedeSyncResult(sede_id=sede_id, sede_code="?", status="error",
                                  error="Sede no existe")
        if not sede.get("drive_spreadsheet_id"):
            return SedeSyncResult(sede_id=sede_id, sede_code=sede["code"],
                                  status="error", error="Sede sin drive_spreadsheet_id")

        result = SedeSyncResult(sede_id=sede_id, sede_code=sede["code"])

        try:
            client = gc or _get_gspread_client()
            sh = client.open_by_key(sede["drive_spreadsheet_id"])
            mat_rows = sh.worksheet("Matriculas").get_all_values()
            asi_rows = sh.worksheet("Asistencia").get_all_values()
        except Exception as e:
            logger.exception("Error leyendo planilla de sede %s", sede["code"])
            result.status = "error"
            result.error = f"Error leyendo planilla: {type(e).__name__}: {e}"
            return result

        try:
            alumnos = parse_matriculas(mat_rows)
            asistencia = parse_asistencia(asi_rows)

            creados, actualizados, corr_map = upsert_alumnos(conn, sede_id, alumnos)
            ruts_vistos = {a["rut_normalizado"] for a in alumnos if a["rut_normalizado"]}
            desaparecidos = marcar_desaparecidos(conn, sede_id, ruts_vistos)
            ins, upd, desc = upsert_asistencia(conn, sede_id, corr_map, asistencia)

            conn.commit()

            result.alumnos_creados = creados
            result.alumnos_actualizados = actualizados
            result.alumnos_desaparecidos = desaparecidos
            result.asistencias_insertadas = ins
            result.asistencias_actualizadas = upd
            result.codigos_desconocidos = desc
            result.status = "ok"
            return result
        except Exception as e:
            conn.rollback()
            logger.exception("Error escribiendo DB para sede %s", sede["code"])
            result.status = "error"
            result.error = f"Error escribiendo DB: {type(e).__name__}: {e}"
            return result
    finally:
        conn.close()


def sync_todas(trigger: str = "manual", actor: Optional[str] = None) -> dict:
    """Sincroniza todas las sedes activas con planilla configurada."""
    run_id = uuid.uuid4()
    started_at = datetime.utcnow()

    conn = db.get_conn()
    try:
        sedes = conn.execute(
            """
            SELECT id, code FROM fundacion.sedes
            WHERE activo = TRUE AND drive_spreadsheet_id IS NOT NULL
            ORDER BY orden, code
            """
        ).fetchall()

        conn.execute(
            """
            INSERT INTO fundacion.sync_logs (run_id, sede_id, status, trigger, actor)
            VALUES (%s, NULL, 'running', %s, %s)
            """,
            (str(run_id), trigger, actor),
        )
        conn.commit()
    finally:
        conn.close()

    client = _get_gspread_client()
    resultados: list[SedeSyncResult] = []

    for sede in sedes:
        r = sync_sede(sede["id"], gc=client)
        resultados.append(r)

        conn = db.get_conn()
        try:
            conn.execute(
                """
                INSERT INTO fundacion.sync_logs (
                    run_id, sede_id, started_at, finished_at, status, trigger, actor,
                    alumnos_creados, alumnos_actualizados, alumnos_desaparecidos,
                    asistencias_insertadas, asistencias_actualizadas, codigos_desconocidos,
                    mensaje
                )
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (str(run_id), r.sede_id, started_at, r.status, trigger, actor,
                 r.alumnos_creados, r.alumnos_actualizados, r.alumnos_desaparecidos,
                 r.asistencias_insertadas, r.asistencias_actualizadas, r.codigos_desconocidos,
                 r.error),
            )
            conn.commit()
        finally:
            conn.close()

    total_ok = sum(1 for r in resultados if r.status == "ok")
    total_err = sum(1 for r in resultados if r.status == "error")
    parent_status = "ok" if total_err == 0 else ("partial" if total_ok > 0 else "error")

    conn = db.get_conn()
    try:
        conn.execute(
            """
            UPDATE fundacion.sync_logs
            SET finished_at = CURRENT_TIMESTAMP, status = %s,
                alumnos_creados = %s, alumnos_actualizados = %s, alumnos_desaparecidos = %s,
                asistencias_insertadas = %s, asistencias_actualizadas = %s,
                codigos_desconocidos = %s
            WHERE run_id = %s AND sede_id IS NULL
            """,
            (parent_status,
             sum(r.alumnos_creados for r in resultados),
             sum(r.alumnos_actualizados for r in resultados),
             sum(r.alumnos_desaparecidos for r in resultados),
             sum(r.asistencias_insertadas for r in resultados),
             sum(r.asistencias_actualizadas for r in resultados),
             sum(r.codigos_desconocidos for r in resultados),
             str(run_id)),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "run_id": str(run_id),
        "status": parent_status,
        "sedes": [
            {
                "sede_id": r.sede_id,
                "sede_code": r.sede_code,
                "status": r.status,
                "alumnos_creados": r.alumnos_creados,
                "alumnos_actualizados": r.alumnos_actualizados,
                "alumnos_desaparecidos": r.alumnos_desaparecidos,
                "asistencias_insertadas": r.asistencias_insertadas,
                "asistencias_actualizadas": r.asistencias_actualizadas,
                "codigos_desconocidos": r.codigos_desconocidos,
                "error": r.error,
            }
            for r in resultados
        ],
    }
