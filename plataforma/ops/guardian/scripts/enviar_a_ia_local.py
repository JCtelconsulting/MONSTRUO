#!/usr/bin/env python3
# Envio a IA local (Ollama) con fallback a cola_envio
# - Lee cola_envio y trata de enviar payload a IA local
# - Si no hay IA local disponible, deja el item en cola y registra ultimo_error
# - Si envio OK, elimina el item de cola y marca paquetes_aprendizaje.enviado_ia_local=1 (si viene paquete_id)

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

def ahora_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def cargar_cfg(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def conectar(db: str) -> sqlite3.Connection:
    con = sqlite3.connect(db, timeout=30)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con

def http_post_json(url: str, data: dict, timeout_s: float) -> dict:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}

def construir_prompt(item: dict) -> str:
    # Prompt minimo, sin secretos
    tipo = item.get("tipo", "desconocido")
    payload = item.get("payload", {})
    return (
        "Analiza este evento/paquete y responde con:\n"
        "1) resumen tecnico (max 6 lineas)\n"
        "2) posible causa raiz (si aplica)\n"
        "3) propuesta concreta (lista de acciones)\n"
        "4) riesgos y verificacion\n\n"
        f"TIPO: {tipo}\n"
        f"PAYLOAD_JSON: {json.dumps(payload, ensure_ascii=False)}\n"
    )

def leer_cola(con: sqlite3.Connection, limite: int) -> List[Tuple[Any, ...]]:
    return con.execute(
        "SELECT id, ts, tipo, payload_json, intentos, ultimo_error FROM cola_envio ORDER BY id ASC LIMIT ?;",
        (limite,),
    ).fetchall()

def actualizar_intento(con: sqlite3.Connection, cola_id: int, err: str) -> None:
    con.execute(
        "UPDATE cola_envio SET intentos = intentos + 1, ultimo_error = ? WHERE id = ?;",
        (err[:1000], cola_id),
    )

def eliminar_cola(con: sqlite3.Connection, cola_id: int) -> None:
    con.execute("DELETE FROM cola_envio WHERE id = ?;", (cola_id,))

def marcar_paquete_enviado(con: sqlite3.Connection, paquete_id: int) -> None:
    con.execute(
        "UPDATE paquetes_aprendizaje SET enviado_ia_local = 1, error_envio = NULL WHERE id = ?;",
        (paquete_id,),
    )

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="/srv/monstruo_dev/plataforma/ops/guardian/config/configuracion_guardian.json")
    ap.add_argument("--limite", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    cfg = cargar_cfg(args.config)
    db = cfg["rutas"]["bd_eventos"]

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3.1")
    url_generate = f"{base_url}/api/generate"

    con = conectar(db)
    enviados = 0
    fallidos = 0
    intentados = 0

    try:
        items = leer_cola(con, args.limite)
        for cola_id, ts, tipo, payload_json, intentos, ultimo_error in items:
            intentados += 1
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except Exception:
                payload = {"payload_crudo": str(payload_json)}

            prompt = construir_prompt({"tipo": tipo, "payload": payload})

            data = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }

            try:
                resp = http_post_json(url_generate, data, timeout_s=args.timeout)
                # Si llego respuesta, consideramos OK
                paquete_id = None
                if isinstance(payload, dict):
                    paquete_id = payload.get("paquete_id")

                if isinstance(paquete_id, int):
                    marcar_paquete_enviado(con, paquete_id)

                eliminar_cola(con, int(cola_id))
                con.commit()
                enviados += 1

            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                err = f"envio_fallido: {type(e).__name__}: {str(e)}"
                actualizar_intento(con, int(cola_id), err)
                con.commit()
                fallidos += 1

            except Exception as e:
                err = f"envio_fallido: {type(e).__name__}: {str(e)}"
                actualizar_intento(con, int(cola_id), err)
                con.commit()
                fallidos += 1

        resumen = {
            "ok": True,
            "ts": ahora_utc_iso(),
            "intentos": intentados,
            "enviados": enviados,
            "fallidos": fallidos,
            "endpoint": url_generate,
            "modelo": model
        }
        print(json.dumps(resumen, ensure_ascii=False))
        return 0

    finally:
        con.close()

if __name__ == "__main__":
    raise SystemExit(main())
