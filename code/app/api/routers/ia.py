from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ia", tags=["ia"])


def _ruta_politicas() -> str:
    # Ruta absoluta estable desde /srv/monstruo
    return os.path.join(os.path.dirname(__file__), "..", "data", "ia", "politicas_central.json")


def _cargar_politicas() -> Dict[str, Any]:
    path = os.path.abspath(_ruta_politicas())
    if not os.path.exists(path):
        return {"version": "0", "politicas_globales": {}, "agentes": [], "reglas_por_modulo": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class PropuestaIA(BaseModel):
    agente_id: str = Field(..., description="ID del agente que propone")
    modulo_objetivo: str = Field(..., description="Modulo impactado (ej: bodega, tks)")
    acciones: List[str] = Field(default_factory=list, description="Acciones propuestas")
    datos: Dict[str, Any] = Field(default_factory=dict, description="Datos de contexto para validar")


class ResultadoValidacion(BaseModel):
    ok: bool
    violaciones: List[Dict[str, Any]]
    timestamp: float


# Memoria simple en proceso (placeholder)
_ULTIMAS_VIOLACIONES: List[Dict[str, Any]] = []


@router.get("/agentes")
def listar_agentes() -> List[Dict[str, Any]]:
    pol = _cargar_politicas()
    agentes = pol.get("agentes", [])
    # Estado basico OK por defecto
    out = []
    for a in agentes:
        out.append({"id": a.get("id"), "nombre": a.get("nombre"), "estado": "OK"})
    return out


@router.get("/violaciones")
def listar_violaciones() -> Dict[str, Any]:
    return {"violaciones": _ULTIMAS_VIOLACIONES[-200:], "timestamp": time.time()}


@router.post("/validar", response_model=ResultadoValidacion)
def validar_propuesta(p: PropuestaIA) -> ResultadoValidacion:
    pol = _cargar_politicas()
    reglas_mod = (pol.get("reglas_por_modulo") or {}).get(p.modulo_objetivo, {})
    violaciones: List[Dict[str, Any]] = []

    # Regla global: no exponer secretos (heuristica simple)
    if pol.get("politicas_globales", {}).get("prohibido_exponer_secretos"):
        texto = json.dumps(p.datos, ensure_ascii=False).lower()
        if "password" in texto or "token" in texto or "apikey" in texto:
            violaciones.append({
                "tipo": "SEGURIDAD",
                "modulo": p.modulo_objetivo,
                "detalle": "Posible exposicion de secreto en datos.",
                "agente_id": p.agente_id
            })

    # Reglas por modulo: campos requeridos
    requeridos = reglas_mod.get("campos_requeridos", [])
    for campo in requeridos:
        if campo not in p.datos:
            violaciones.append({
                "tipo": "POLITICA_MODULO",
                "modulo": p.modulo_objetivo,
                "detalle": f"Falta campo requerido: {campo}",
                "agente_id": p.agente_id
            })

    # Reglas por modulo: acciones prohibidas
    prohibidas = set(reglas_mod.get("acciones_prohibidas", []))
    for accion in p.acciones:
        if accion in prohibidas:
            violaciones.append({
                "tipo": "POLITICA_MODULO",
                "modulo": p.modulo_objetivo,
                "detalle": f"Accion prohibida: {accion}",
                "agente_id": p.agente_id
            })

    ok = len(violaciones) == 0
    res = ResultadoValidacion(ok=ok, violaciones=violaciones, timestamp=time.time())

    # Guardar historial (placeholder)
    if violaciones:
        _ULTIMAS_VIOLACIONES.extend(violaciones)

    return res
