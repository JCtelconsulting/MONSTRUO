"""Autocompletador por audio (IA) — servicio, modo LOCAL (sin claves cloud).

Pieza 1 (STT): transcribe el audio con faster-whisper LOCAL (CPU), modelo chico.
Pieza 3 (propuesta): un LLM LOCAL vía Ollama (API compatible con OpenAI) recibe la
transcripción + las fotos (si el modelo es de visión) + el contexto y propone la
estructura del informe.

Config por entorno (ops/environments/.env):
  OLLAMA_BASE_URL   p.ej. http://192.168.60.50:11434/v1   (el PC con Ollama)
  OLLAMA_MODEL      p.ej. qwen2.5vl:3b / llava:7b / llama3.2:3b   (default qwen2.5vl:3b)
  WHISPER_MODEL     tiny|base|small   (default base)
  WHISPER_DEVICE    cpu|cuda          (default cpu)

INERTE si falta config: lanza RuntimeError con mensaje claro (-> 503).
Ver docs/AUTOCOMPLETADOR_AUDIO.md.
"""

import base64
import json
import os
from typing import Any, Dict, List

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "").strip()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5vl:3b").strip()
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base").strip()
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu").strip()
MODELO_IA = OLLAMA_MODEL  # nombre para mostrar en la UI

_whisper = None


def _stt_disponible() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


def disponible() -> Dict[str, bool]:
    """Qué piezas están configuradas (modo local)."""
    return {"stt": _stt_disponible(), "ia": bool(OLLAMA_BASE_URL)}


def transcribir(audio_path: str) -> str:
    """Audio -> texto con faster-whisper local. RuntimeError si no está instalado."""
    global _whisper
    if not _stt_disponible():
        raise RuntimeError(
            "STT local no disponible: falta 'faster-whisper' (pip install faster-whisper)."
        )
    from faster_whisper import WhisperModel

    if _whisper is None:
        _whisper = WhisperModel(
            WHISPER_MODEL, device=WHISPER_DEVICE, compute_type="int8"
        )
    segments, _info = _whisper.transcribe(audio_path, language="es")
    return " ".join(s.text.strip() for s in segments).strip()


PROPUESTA_SCHEMA = {
    "hitos": [
        {
            "categoria": "str (Antes/Durante/Despues u otra del proyecto)",
            "item": "str (nombre del hito/item sugerido)",
            "fotos": "[int] (índices de las fotos que corresponden)",
            "comentario": "str (comentario sugerido para el informe)",
            "confianza": "float 0..1",
            "duda": "str (vacío si no hay)",
        }
    ],
    "caso_uso": "str (uno de los 7 casos de Diego)",
    "resumen": "str (qué se hizo, 1-2 frases)",
}

_PROMPT = """Eres un asistente que estructura informes de terreno para Terreneitor
(Telconsulting). El técnico grabó un RELATO hablado (no un dictado) de lo que hizo
y subió FOTOS. ENTIENDE el relato aunque sea desordenado y PROPÓN la estructura del
informe, mapeando cada foto al hito que corresponde.

Casos de uso (elige el más probable): 1) Instalación de servicios, 2) Retiro de
equipamiento, 3) Traslado de servicios, 4) Despacho de equipamiento, 5)
Reportabilidad remota con EPP, 6) Respaldo de producción/avance del día, 7) Visita
técnica/preventa.

Reglas: NO inventes; si algo no queda claro ponlo en "duda" y baja "confianza";
las fotos se referencian por índice 0-based. Responde SOLO un JSON con esta forma:
{schema}

Contexto del proyecto:
{contexto}

Transcripción del relato:
{transcripcion}
"""


def proponer_estructura(
    transcripcion: str, fotos_paths: List[str], contexto: Dict[str, Any]
) -> Dict[str, Any]:
    """LLM local (Ollama, API estilo OpenAI) propone la estructura del informe."""
    if not OLLAMA_BASE_URL:
        raise RuntimeError(
            "IA local no configurada: falta OLLAMA_BASE_URL (el PC con Ollama)."
        )
    from openai import OpenAI  # SDK ya presente; apuntado a Ollama

    client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    texto = _PROMPT.format(
        schema=json.dumps(PROPUESTA_SCHEMA, ensure_ascii=False),
        contexto=json.dumps(contexto, ensure_ascii=False),
        transcripcion=transcripcion,
    )
    content: List[Dict[str, Any]] = [{"type": "text", "text": texto}]
    for p in fotos_paths[:8]:  # límite prudente para modelos livianos
        try:
            with open(p, "rb") as fh:
                b64 = base64.standard_b64encode(fh.read()).decode()
            media = (
                "image/jpeg" if p.lower().endswith((".jpg", ".jpeg")) else "image/png"
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media};base64,{b64}"},
                }
            )
        except Exception:
            continue

    resp = client.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": content}],
        temperature=0.2,
    )
    out = (resp.choices[0].message.content or "").strip()
    ini, fin = out.find("{"), out.rfind("}")
    if ini == -1 or fin == -1:
        return {"error": "El modelo no devolvió JSON", "raw": out[:500]}
    try:
        return json.loads(out[ini : fin + 1])
    except json.JSONDecodeError:
        return {"error": "JSON inválido del modelo", "raw": out[:500]}
