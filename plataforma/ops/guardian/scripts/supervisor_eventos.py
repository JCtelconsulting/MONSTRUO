#!/usr/bin/env python3
# Supervisor de eventos (MONSTRUO)
# - Lee eventos nuevos desde SQLite
# - Genera paquetes de aprendizaje (tabla paquetes_aprendizaje)
# - Encola payloads en cola_envio (tabla cola_envio)
# - No modifica codigo; solo BD/estado

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

def ahora_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def cargar_json(path: str, default: dict) -> dict:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)

def cargar_cfg(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def conectar(db: str) -> sqlite3.Connection:
    con = sqlite3.connect(db, timeout=30)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con

def existe_paquete_para_evento(con: sqlite3.Connection, evento_id: int) -> bool:
    # Dedup simple: buscar evento_id dentro de cambios_json
    q = "SELECT 1 FROM paquetes_aprendizaje WHERE cambios_json LIKE ? LIMIT 1;"
    like = f'%"evento_id": {evento_id}%'
    return con.execute(q, (like,)).fetchone() is not None

def insertar_paquete(
    con: sqlite3.Connection,
    hito: Optional[str],
    objetivo: str,
    sintoma: str,
    causa_raiz: Optional[str],
    cambios: dict,
    verificacion: str,
    correccion_humana: Optional[str],
    etiquetas: List[str],
) -> int:
    ts = ahora_utc_iso()
    cambios_json = json.dumps(cambios, ensure_ascii=False)
    etiquetas_json = json.dumps(etiquetas, ensure_ascii=False)
    cur = con.execute(
        """
        INSERT INTO paquetes_aprendizaje(
          ts, hito, objetivo, sintoma, causa_raiz,
          cambios_json, verificacion, correccion_humana, etiquetas_json,
          enviado_ia_local, error_envio
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL);
        """,
        (ts, hito, objetivo, sintoma, causa_raiz, cambios_json, verificacion, correccion_humana, etiquetas_json),
    )
    return int(cur.lastrowid)

def encolar(con: sqlite3.Connection, tipo: str, payload: dict) -> int:
    ts = ahora_utc_iso()
    payload_json = json.dumps(payload, ensure_ascii=False)
    cur = con.execute(
        """
        INSERT INTO cola_envio(ts, tipo, payload_json, intentos, ultimo_error)
        VALUES (?, ?, ?, 0, NULL);
        """,
        (ts, tipo, payload_json),
    )
    return int(cur.lastrowid)

def procesar_evento(con: sqlite3.Connection, ev: Tuple[Any, ...]) -> Dict[str, int]:
    # ev: (id, ts, tipo, severidad, origen, ruta, resumen, detalle_json)
    evento_id, ts, tipo, severidad, origen, ruta, resumen, detalle_json = ev
    res = {"paquetes": 0, "cola": 0}

    if existe_paquete_para_evento(con, int(evento_id)):
        return res

    detalle = None
    if detalle_json:
        try:
            detalle = json.loads(detalle_json)
        except Exception:
            detalle = {"detalle_crudo": str(detalle_json)}

    if tipo == "regla_nombre_prohibido" and severidad == "CRITICAL":
        objetivo = "Cumplimiento de reglas de archivos"
        sintoma = f"Nombre prohibido detectado: {ruta or '(sin ruta)'}"
        causa = "Se detecto un archivo con patron prohibido fuera de backups/"
        cambios = {"evento_id": int(evento_id), "tipo": tipo, "ruta": ruta, "detalle": detalle}
        verif = "Revisar el archivo y moverlo a backups/YYYY-MM-DD/ o corregir el nombre segun reglas"
        pid = insertar_paquete(con, None, objetivo, sintoma, causa, cambios, verif, None, ["guardian", "reglas", "backups"])
        encolar(con, "alerta", {"evento_id": int(evento_id), "paquete_id": pid, "severidad": severidad, "resumen": resumen, "ruta": ruta})
        res["paquetes"] += 1
        res["cola"] += 1
        return res

    if tipo == "registro_error_detectado" and severidad in ("CRITICAL", "WARN"):
        objetivo = "Diagnostico de error desde registros"
        sintoma = f"Error en registros: {resumen}"
        causa = None
        cambios = {"evento_id": int(evento_id), "tipo": tipo, "origen": origen, "ruta": ruta, "detalle": detalle}
        verif = "Correlacionar con logs completos y reproducir el error si aplica"
        pid = insertar_paquete(con, None, objetivo, sintoma, causa, cambios, verif, None, ["guardian", "registros", "errores"])
        encolar(con, "analisis_registros", {"evento_id": int(evento_id), "paquete_id": pid, "severidad": severidad, "resumen": resumen})
        res["paquetes"] += 1
        res["cola"] += 1
        return res

    return res

def leer_eventos_nuevos(con: sqlite3.Connection, ultimo_id: int, max_eventos: int) -> List[Tuple[Any, ...]]:
    q = """
    SELECT id, ts, tipo, severidad, origen, ruta, resumen, detalle_json
    FROM eventos
    WHERE id > ?
    ORDER BY id ASC
    LIMIT ?;
    """
    return con.execute(q, (ultimo_id, max_eventos)).fetchall()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="/srv/monstruo_dev/plataforma/ops/guardian/config/configuracion_guardian.json")
    ap.add_argument("--estado", default="/srv/monstruo_dev/plataforma/ops/guardian/estado_supervisor.json")
    ap.add_argument("--intervalo", type=float, default=3.0)
    ap.add_argument("--max_eventos", type=int, default=200)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    cfg = cargar_cfg(args.config)
    db = cfg["rutas"]["bd_eventos"]

    estado = cargar_json(args.estado, {"ultimo_evento_id": 0})
    ultimo = int(estado.get("ultimo_evento_id", 0))

    con = conectar(db)
    try:
        while True:
            eventos = leer_eventos_nuevos(con, ultimo, args.max_eventos)
            if not eventos and args.once:
                break

            paquetes = 0
            cola = 0
            for ev in eventos:
                ultimo = int(ev[0])
                r = procesar_evento(con, ev)
                paquetes += r["paquetes"]
                cola += r["cola"]

            if eventos:
                con.commit()

            estado["ultimo_evento_id"] = ultimo
            estado["ts_ultima_ejecucion"] = ahora_utc_iso()
            estado["resumen_ultima_ejecucion"] = {"eventos_leidos": len(eventos), "paquetes_creados": paquetes, "cola_encolada": cola}
            guardar_json(args.estado, estado)

            if args.once:
                break
            time.sleep(max(0.2, args.intervalo))
    finally:
        con.close()

    print(json.dumps({"ok": True, "ultimo_evento_id": ultimo, "estado": estado.get("resumen_ultima_ejecucion")}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
