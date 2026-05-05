"""
Tests unitarios de fundación — control de scope (sede/curso por usuario).

Sin DB ni docker. Cubren la lógica pura de _is_target_in_scope que decide
si un usuario puede ver/editar una tarea según su scope asignado.

Ejecutar:
    pytest fundacion/tests/test_scope_unit.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fundacion.backend.router import _is_target_in_scope


class TestScopeGlobal:
    """Usuarios con is_global=True pueden ver todo."""

    def test_global_acepta_cualquier_sede_curso(self):
        scope = {"is_global": True, "sedes": [], "cursos": []}
        assert _is_target_in_scope(scope, "la_pintana", "kinder") is True
        assert _is_target_in_scope(scope, "maipu", "primero_basico") is True
        assert _is_target_in_scope(scope, "", "") is True


class TestScopePorSede:
    """Usuarios con sedes específicas solo ven esas."""

    def test_sede_permitida(self):
        scope = {"is_global": False, "sedes": ["la_pintana"], "cursos": []}
        assert _is_target_in_scope(scope, "la_pintana", "kinder") is True

    def test_sede_no_permitida_rechaza(self):
        scope = {"is_global": False, "sedes": ["la_pintana"], "cursos": []}
        assert _is_target_in_scope(scope, "maipu", "kinder") is False

    def test_multiple_sedes(self):
        scope = {"is_global": False, "sedes": ["la_pintana", "maipu"], "cursos": []}
        assert _is_target_in_scope(scope, "la_pintana", "kinder") is True
        assert _is_target_in_scope(scope, "maipu", "kinder") is True
        assert _is_target_in_scope(scope, "renca", "kinder") is False


class TestScopePorCurso:
    """Usuarios con cursos específicos solo ven esos cursos."""

    def test_curso_permitido(self):
        scope = {"is_global": False, "sedes": [], "cursos": ["kinder"]}
        assert _is_target_in_scope(scope, "la_pintana", "kinder") is True

    def test_curso_no_permitido_rechaza(self):
        scope = {"is_global": False, "sedes": [], "cursos": ["kinder"]}
        assert _is_target_in_scope(scope, "la_pintana", "primero_basico") is False


class TestScopeCombinadoSedeCurso:
    """Sede AND curso deben coincidir si ambos están definidos."""

    def test_ambos_correctos_pasa(self):
        scope = {"is_global": False, "sedes": ["la_pintana"], "cursos": ["kinder"]}
        assert _is_target_in_scope(scope, "la_pintana", "kinder") is True

    def test_sede_correcta_curso_incorrecto_falla(self):
        scope = {"is_global": False, "sedes": ["la_pintana"], "cursos": ["kinder"]}
        assert _is_target_in_scope(scope, "la_pintana", "primero_basico") is False

    def test_sede_incorrecta_curso_correcto_falla(self):
        scope = {"is_global": False, "sedes": ["la_pintana"], "cursos": ["kinder"]}
        assert _is_target_in_scope(scope, "maipu", "kinder") is False


class TestScopeVacio:
    """Scope sin restricciones (sedes y cursos vacíos pero no global)."""

    def test_scope_sin_restricciones_acepta_todo(self):
        # Si no hay sedes ni cursos definidos pero is_global=False,
        # se considera "no hay restricciones por rol" → acepta cualquiera
        scope = {"is_global": False, "sedes": [], "cursos": []}
        assert _is_target_in_scope(scope, "la_pintana", "kinder") is True
