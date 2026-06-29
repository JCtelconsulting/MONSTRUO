"""Catálogo CANÓNICO de áreas de la empresa (organigrama).

Fuente ÚNICA de verdad de las áreas/roles operativos de Monstruo. Vive en la base
(plataforma/core) y cada módulo la IMPORTA como código estático — así todos los
módulos usan los MISMOS nombres de áreas/roles (se entiende la app sin enredo),
pero sin acoplar el runtime: es una constante en el proceso de cada módulo, no un
servicio vivo, así que si un módulo se cae los demás siguen.

Principio: el ROL operativo de una persona ES su área. La gestión global
(admin, encargado de mesa) no es un área: ve todo.

Este es el catálogo de las áreas INTERNAS de la empresa, comunes a Ticketera y GTA.
'pmo' es el área de gestión de proyectos: el MÓDULO pmo se eliminó, pero el ÁREA es
real y se usa en GTA. Se EXCLUYEN: ia y zabbix (no son áreas; zabbix se integrará por
API), y las áreas EXTERNAS que solo maneja GTA (contabilidad, prevención de riesgos) —
esas no son del organigrama interno ni aparecen en Ticketera; GTA las tiene aparte,
además de este catálogo.
"""
from __future__ import annotations

from typing import Dict, List

# slug -> etiqueta visible. El orden es el de presentación en la UI.
AREAS: Dict[str, str] = {
    "comercial": "Comercial",
    "preventa": "Preventa",
    "pmo": "PMO",
    "sistemas": "Sistemas",
    "redes": "Redes",
    "bodega": "Bodega",
    "proveedores": "Proveedores",
    "finanzas": "Finanzas",
    "capital_humano": "Capital Humano",
    "gerencia": "Gerencia",
}

# Emoji por área (para chips/filtros de la UI). Vive acá para que el frontend NO mantenga
# un espejo manual y no se desincronice (fue la causa de un bug: 'pmo' faltaba en la UI).
AREA_EMOJI: Dict[str, str] = {
    "comercial": "🤝",
    "preventa": "📋",
    "pmo": "📊",
    "sistemas": "💻",
    "redes": "🌐",
    "bodega": "📦",
    "proveedores": "🚚",
    "finanzas": "💰",
    "capital_humano": "👥",
    "gerencia": "👔",
}

# Pseudo-área para los tickets que aún no tienen área asignada (no es un área de
# personas; siempre disponible para no perder tickets sin clasificar).
SIN_AREA = "general"
SIN_AREA_LABEL = "Sin área asignada"
SIN_AREA_EMOJI = "📭"


def area_meta() -> Dict[str, Dict[str, str]]:
    """Catálogo {code: {label, emoji}} de las áreas + 'general'. Fuente única para la UI."""
    meta = {code: {"label": AREAS[code], "emoji": AREA_EMOJI.get(code, "")} for code in AREAS}
    meta[SIN_AREA] = {"label": SIN_AREA_LABEL, "emoji": SIN_AREA_EMOJI}
    return meta

# Roles de GESTIÓN GLOBAL: no son un área, ven todo.
ROLES_GESTION_GLOBAL = {"admin", "encargado_mesa"}

# Alias de roles legacy -> área canónica actual (los roles ahora SON las áreas; estos cubren
# datos viejos que aún no se migraron). ops e implementaciones se unificaron en pmo.
ALIAS_ROL_AREA: Dict[str, str] = {
    "warehouse": "bodega",
    "finance": "finanzas",
    "ops": "pmo",
    "implementaciones": "pmo",
    "ejecucion": SIN_AREA,
}


def es_area(slug: str) -> bool:
    return str(slug or "").strip().lower() in AREAS


def label_area(slug: str) -> str:
    s = str(slug or "").strip().lower()
    if s == SIN_AREA:
        return SIN_AREA_LABEL
    return AREAS.get(s, s)


def rol_a_area(rol: str) -> str:
    """Área canónica de un rol/especialidad. '' si es gestión global o desconocido."""
    r = str(rol or "").strip().lower()
    if r in ROLES_GESTION_GLOBAL:
        return ""
    if r in AREAS:
        return r
    return ALIAS_ROL_AREA.get(r, "")


def slugs_areas() -> List[str]:
    return list(AREAS.keys())
