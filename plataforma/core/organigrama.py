"""Catálogo CANÓNICO de áreas de la empresa (organigrama).

Fuente ÚNICA de verdad de las áreas/roles operativos de Monstruo. Vive en la base
(plataforma/core) y cada módulo la IMPORTA como código estático — así todos los
módulos usan los MISMOS nombres de áreas/roles (se entiende la app sin enredo),
pero sin acoplar el runtime: es una constante en el proceso de cada módulo, no un
servicio vivo, así que si un módulo se cae los demás siguen.

Principio: el ROL operativo de una persona ES su área. La gestión global
(admin, encargado de mesa) no es un área: ve todo.

Áreas tomadas del organigrama real (reusando los slugs que ya usa GTA). Se
excluyen a propósito: pmo (lo reemplaza GTA), ia y zabbix (no son áreas; zabbix
se integrará por API), y las externas (prevención de riesgos, contabilidad).
"""
from __future__ import annotations

from typing import Dict, List

# slug -> etiqueta visible. El orden es el de presentación en la UI.
AREAS: Dict[str, str] = {
    "comercial": "Comercial",
    "preventa": "Preventa",
    "sistemas": "Sistemas",
    "redes": "Redes",
    "bodega": "Bodega",
    "proveedores": "Proveedores",
    "finanzas": "Finanzas",
    "capital_humano": "Capital Humano",
    "gerencia": "Gerencia",
}

# Pseudo-área para los tickets que aún no tienen área asignada (no es un área de
# personas; siempre disponible para no perder tickets sin clasificar).
SIN_AREA = "general"
SIN_AREA_LABEL = "Sin área asignada"

# Roles de GESTIÓN GLOBAL: no son un área, ven todo.
ROLES_GESTION_GLOBAL = {"admin", "encargado_mesa"}

# Alias de roles/especialidades legacy -> área canónica (para datos/usuarios viejos).
ALIAS_ROL_AREA: Dict[str, str] = {
    "warehouse": "bodega",
    "ops": SIN_AREA,
    "implementaciones": SIN_AREA,
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
