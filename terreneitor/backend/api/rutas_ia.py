"""Autocompletador por audio (IA) — endpoints.

Scaffold feature-flagged: si faltan las claves (OPENAI_API_KEY / ANTHROPIC_API_KEY)
responde 503 con un mensaje claro, sin romper nada. Ver docs/AUTOCOMPLETADOR_AUDIO.md.
"""

import json
import os
import shutil
import tempfile
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from terreneitor.backend import dependencias, nucleo
from terreneitor.backend.services import ia_autocompletador

router = APIRouter(
    prefix="/api/ia",
    tags=["IA"],
    dependencies=[Depends(dependencias.require_session)],
)


@router.get("/estado")
def estado_ia():
    """Qué piezas de IA están configuradas (para que la UI muestre/oculte el botón)."""
    d = ia_autocompletador.disponible()
    return {
        "stt": d["stt"],
        "ia": d["ia"],
        "listo": d["stt"] and d["ia"],
        "modelo_ia": ia_autocompletador.MODELO_IA,
    }


@router.post("/autocompletar")
def autocompletar(
    audio: UploadFile = File(...),
    contexto: str = Form("{}"),
    fotos: Optional[str] = Form(None),  # JSON: lista de rutas absolutas de fotos
):
    """Recibe un audio (+ contexto + rutas de fotos), transcribe y propone la
    estructura del informe. 503 si la IA no está configurada."""
    d = ia_autocompletador.disponible()
    if not (d["stt"] and d["ia"]):
        faltan = []
        if not d["stt"]:
            faltan.append("faster-whisper (transcripción local)")
        if not d["ia"]:
            faltan.append("OLLAMA_BASE_URL (LLM local en el PC)")
        raise HTTPException(
            status_code=503,
            detail="Autocompletador IA local no configurado. Faltan: "
            + ", ".join(faltan),
        )

    try:
        ctx = json.loads(contexto or "{}")
    except json.JSONDecodeError:
        ctx = {}
    foto_paths: List[str] = []
    if fotos:
        try:
            foto_paths = [p for p in json.loads(fotos) if isinstance(p, str)]
        except json.JSONDecodeError:
            foto_paths = []
    # validar fotos dentro de BASE_FILES_DIR (anti path traversal)
    base = os.path.realpath(nucleo.BASE_FILES_DIR)
    foto_paths = [
        p for p in foto_paths if os.path.realpath(p).startswith(base + os.sep)
    ]

    tmp = None
    try:
        suf = os.path.splitext(audio.filename or "audio.m4a")[1] or ".m4a"
        fd, tmp = tempfile.mkstemp(suffix=suf)
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(audio.file, out)
        transcripcion = ia_autocompletador.transcribir(tmp)
        propuesta = ia_autocompletador.proponer_estructura(
            transcripcion, foto_paths, ctx
        )
        return {"transcripcion": transcripcion, "propuesta": propuesta}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:  # noqa: B904
        raise HTTPException(status_code=500, detail=f"Error IA: {e}")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
