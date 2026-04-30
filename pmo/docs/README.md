# PMO — Documentación

Oficina de Proyectos. Gestión de proyectos técnicos e implementaciones.

## Estructura

```
pmo/
├── backend/       # Lógica de negocio y API (FastAPI)
├── ui/            # Frontend (HTML + JS + CSS)
├── migrations/    # Migraciones SQL versionadas
├── tests/         # Tests de integración y unitarios
├── scripts/       # Scripts de utilidad y administración
├── docs/          # Esta carpeta — documentación del módulo
└── data/          # Datos locales del módulo (no subir a git datos sensibles)
```

## API

Prefijo: `/api/pmo/`

Ver `backend/router.py` para los endpoints disponibles.

## Tests

```bash
pytest pmo/tests/ -v
```

## Migraciones

Ver `migrations/README.md` para instrucciones.
