# El orden de estos imports importa: core+models deben cargar antes
# que api/* porque rutas_*.py hace `from backend import dependencias,
# modelos, nucleo` y necesita esos nombres ya bindeados al namespace.
# Por eso desactivamos isort/I001 en este archivo.
# ruff: noqa: I001
from .core import dependencias, nucleo
from .models import modelos
from .api import (
    rutas_admin,
    rutas_auth,
    rutas_gerencia,
    rutas_health,
    rutas_ia,
    rutas_reportes,
    rutas_scanner,
    rutas_supervisor,
    rutas_terreno,
)
