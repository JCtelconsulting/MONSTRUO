"""
Tests unitarios de GTA — funciones puras, sin DB.

Cubren cálculo de SLA, parseo de definición de pasos, transiciones de color
del semáforo. Rápidos (segundos), no requieren docker ni Postgres.

Ejecutar:
    pytest gta/tests/test_sla_unit.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gta.backend.services import flujos


def _tarea(**overrides):
    base = {
        "sla_horas": 4,
        "estado": "lista",
        "inicio_at": None,
        "sla_paused_minutes": 0,
        "sla_pause_started_at": None,
        "ejecutor_completo_at": None,
        "validado_at": None,
    }
    base.update(overrides)
    return base


class TestCalcularSlaPct:
    """flujos.calcular_sla_pct — función pura, sin DB."""

    def test_sin_sla_horas_devuelve_gray(self):
        out = flujos.calcular_sla_pct(_tarea(sla_horas=0))
        assert out["color"] == "gray"
        assert out["pct"] == 0
        assert out["vencida"] is False

    def test_sin_inicio_at_devuelve_gray(self):
        out = flujos.calcular_sla_pct(_tarea(inicio_at=None))
        assert out["color"] == "gray"
        assert out["pct"] == 0
        assert out["minutos_total"] == 4 * 60

    def test_estado_lista_color_cyan_con_sla_bajo(self):
        ahora = datetime.now(timezone.utc)
        inicio = ahora - timedelta(minutes=30)
        out = flujos.calcular_sla_pct(_tarea(
            estado="lista",
            inicio_at=inicio.isoformat(),
        ))
        assert out["color"] == "cyan"
        assert 10 <= out["pct"] <= 15
        assert out["vencida"] is False

    def test_color_amarillo_a_70_pct(self):
        ahora = datetime.now(timezone.utc)
        inicio = ahora - timedelta(minutes=175)
        out = flujos.calcular_sla_pct(_tarea(estado="en_progreso", inicio_at=inicio.isoformat()))
        assert out["color"] == "yellow"

    def test_color_naranja_a_85_pct(self):
        ahora = datetime.now(timezone.utc)
        inicio = ahora - timedelta(minutes=210)
        out = flujos.calcular_sla_pct(_tarea(estado="en_progreso", inicio_at=inicio.isoformat()))
        assert out["color"] == "orange"

    def test_color_rojo_y_vencida_a_100_pct(self):
        ahora = datetime.now(timezone.utc)
        inicio = ahora - timedelta(minutes=300)
        out = flujos.calcular_sla_pct(_tarea(estado="en_progreso", inicio_at=inicio.isoformat()))
        assert out["color"] == "red"
        assert out["vencida"] is True
        assert out["pct"] >= 100

    def test_completada_a_tiempo_color_verde(self):
        inicio = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
        fin = inicio + timedelta(hours=2)
        out = flujos.calcular_sla_pct(_tarea(
            estado="completada",
            inicio_at=inicio.isoformat(),
            ejecutor_completo_at=fin.isoformat(),
        ))
        assert out["color"] == "green"
        assert out["vencida"] is False

    def test_completada_pero_tarde_color_rojo_completado(self):
        inicio = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
        fin = inicio + timedelta(hours=5)
        out = flujos.calcular_sla_pct(_tarea(
            estado="completada",
            inicio_at=inicio.isoformat(),
            ejecutor_completo_at=fin.isoformat(),
        ))
        assert out["color"] == "rojo_completado"

    def test_ayuda_pedida_pausa_sla(self):
        inicio = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
        pausa_iniciada = inicio + timedelta(hours=1)
        out = flujos.calcular_sla_pct(_tarea(
            estado="ayuda_pedida",
            inicio_at=inicio.isoformat(),
            sla_pause_started_at=pausa_iniciada.isoformat(),
        ))
        assert out["esta_pausada"] is True
        assert 20 <= out["pct"] <= 30

    def test_minutos_pausados_se_descuentan(self):
        ahora = datetime.now(timezone.utc)
        inicio = ahora - timedelta(minutes=180)
        out = flujos.calcular_sla_pct(_tarea(
            estado="en_progreso",
            inicio_at=inicio.isoformat(),
            sla_paused_minutes=60,
        ))
        assert 45 <= out["pct"] <= 55

    def test_estado_cancelada_color_gray(self):
        ahora = datetime.now(timezone.utc)
        inicio = ahora - timedelta(hours=10)
        out = flujos.calcular_sla_pct(_tarea(estado="cancelada", inicio_at=inicio.isoformat()))
        assert out["color"] == "gray"

    def test_estado_por_validar_color_blue(self):
        ahora = datetime.now(timezone.utc)
        inicio = ahora - timedelta(minutes=60)
        out = flujos.calcular_sla_pct(_tarea(estado="por_validar", inicio_at=inicio.isoformat()))
        assert out["color"] == "blue"


class TestParsePasosDefinicion:
    """flujos._parse_pasos_definicion — acepta formato viejo y nuevo."""

    def test_input_vacio(self):
        assert flujos._parse_pasos_definicion(None) == []
        assert flujos._parse_pasos_definicion([]) == []
        assert flujos._parse_pasos_definicion("") == []

    def test_lista_de_strings_formato_viejo(self):
        result = flujos._parse_pasos_definicion(["Paso A", "Paso B"])
        assert isinstance(result, list)
        assert len(result) == 2

    def test_lista_de_dicts_formato_nuevo(self):
        pasos = [
            {"orden": 1, "titulo": "Comercial", "area_code": "comercial", "sla_horas": 4},
            {"orden": 2, "titulo": "Sistemas", "area_code": "sistemas", "sla_horas": 8, "depende_de": [1]},
        ]
        result = flujos._parse_pasos_definicion(pasos)
        assert len(result) == 2

    def test_json_string_se_parsea(self):
        result = flujos._parse_pasos_definicion('["A", "B"]')
        assert len(result) == 2
