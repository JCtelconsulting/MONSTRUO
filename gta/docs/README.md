# Gta — Documentación

Gestión de Tareas Automatizada. Solicitudes entre áreas, procesos guiados y quiebres de proceso.

## Estructura

```
gta/
├── backend/       # Lógica de negocio y API (FastAPI)
├── ui/            # Frontend (HTML + JS + CSS)
├── migrations/    # Migraciones SQL versionadas
├── tests/         # Tests de integración y unitarios
├── scripts/       # Scripts de utilidad y administración
├── docs/          # Esta carpeta — documentación del módulo
└── data/          # Datos locales del módulo (no subir a git datos sensibles)
```

## API

Prefijo: `/api/gta/`

Ver `backend/router.py` para los endpoints disponibles.

## Tests

```bash
pytest gta/tests/ -v
```

## Migraciones

Ver `migrations/README.md` para instrucciones.
