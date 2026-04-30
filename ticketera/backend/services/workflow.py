from __future__ import annotations

from typing import Dict, List, Optional

TIPOS_TICKET_VALIDOS = {"incidencia", "requerimiento", "cambio"}

SUBESTADOS_VALIDOS = {
    "recibido",
    "asignado",
    "en_analisis",
    "pendiente_compra",
    "pendiente_cliente",
    "pendiente_tercero",
    "pendiente_aprobacion_1",
    "pendiente_aprobacion_2",
    "aprobado",
    "rechazado",
    "en_ejecucion",
    "en_validacion",
    "reabierto",
    "en_progreso",
    "resuelto",
    "cerrado",
}

SUBESTADOS_ESPERA = {
    "pendiente_compra",
    "pendiente_cliente",
    "pendiente_tercero",
}

SUBESTADOS_LEGACY_MAP = {
    "nuevo": "recibido",
    "triage": "recibido",
}

WORKFLOW_RULES: Dict[str, Dict[str, List[str]]] = {
    "incidencia": {
        "recibido": ["asignado"],
        "asignado": ["en_progreso"],
        "pendiente_cliente": ["en_progreso"],
        "pendiente_compra": ["en_progreso"],
        "pendiente_tercero": ["en_progreso"],
        "en_progreso": ["resuelto", "pendiente_cliente", "pendiente_compra", "pendiente_tercero"],
        "resuelto": ["cerrado", "reabierto"],
        "cerrado": ["en_progreso", "reabierto"],
        "reabierto": ["en_progreso"],
    },
    "requerimiento": {
        "recibido": ["asignado"],
        "en_analisis": ["asignado", "en_progreso"],  # legacy
        "asignado": ["en_analisis", "en_progreso"],
        "pendiente_cliente": ["en_progreso"],
        "pendiente_compra": ["en_progreso"],
        "pendiente_tercero": ["en_progreso"],
        "en_progreso": ["resuelto", "en_validacion", "pendiente_cliente", "pendiente_compra", "pendiente_tercero"],
        "en_validacion": ["resuelto", "en_progreso", "cerrado"],  # legacy cierre directo
        "resuelto": ["cerrado", "reabierto"],
        "cerrado": ["en_progreso", "reabierto"],
        "reabierto": ["en_progreso"],
    },
    "cambio": {
        "recibido": ["asignado"],
        "asignado": ["en_analisis"],
        "pendiente_cliente": ["en_ejecucion", "en_progreso"],
        "pendiente_compra": ["en_ejecucion", "en_progreso"],
        "pendiente_tercero": ["en_ejecucion", "en_progreso"],
        "en_analisis": ["pendiente_aprobacion_1"],
        "pendiente_aprobacion_1": ["pendiente_aprobacion_2", "rechazado"],
        "pendiente_aprobacion_2": ["aprobado", "rechazado"],
        "aprobado": ["en_ejecucion"],
        "en_ejecucion": ["en_validacion", "pendiente_cliente", "pendiente_compra", "pendiente_tercero"],
        "en_validacion": ["resuelto", "en_progreso", "cerrado"],  # legacy cierre directo
        "resuelto": ["cerrado", "reabierto"],
        "rechazado": ["en_analisis"],
        "cerrado": ["en_progreso", "reabierto"],
        "reabierto": ["en_progreso"],
    },
}


def normalize_ticket_type(value: Optional[str]) -> str:
    normalized = (value or "incidencia").strip().lower()
    if normalized not in TIPOS_TICKET_VALIDOS:
        return "incidencia"
    return normalized


def normalize_subestado(value: Optional[str], default_value: str = "recibido") -> str:
    raw_default = str(default_value or "recibido").strip().lower()
    normalized_default = SUBESTADOS_LEGACY_MAP.get(raw_default, raw_default) or "recibido"
    if normalized_default not in SUBESTADOS_VALIDOS:
        normalized_default = "recibido"

    raw = str(value or normalized_default).strip().lower()
    normalized = SUBESTADOS_LEGACY_MAP.get(raw, raw)
    if normalized not in SUBESTADOS_VALIDOS:
        return normalized_default
    return normalized


def workflow_next(tipo: str, subestado: str) -> List[str]:
    rules = WORKFLOW_RULES.get(normalize_ticket_type(tipo), WORKFLOW_RULES["incidencia"])
    return list(rules.get(normalize_subestado(subestado), []))


def can_transition(tipo: str, from_subestado: str, to_subestado: str) -> bool:
    allowed = workflow_next(tipo, from_subestado)
    return normalize_subestado(to_subestado) in allowed


def normalize_transition_target(from_subestado: str, requested_subestado: Optional[str]) -> str:
    from_norm = normalize_subestado(from_subestado, "recibido")
    raw_target = str(requested_subestado or "").strip().lower()
    if raw_target == "triage":
        if from_norm == "recibido":
            return "asignado"
        return from_norm
    return normalize_subestado(requested_subestado, from_norm)

