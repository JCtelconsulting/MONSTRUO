# Gateway — Documentación

Proxy central, autenticación, sidebar compartido y dashboard. Todas las requests pasan por aquí.

## Estructura

```
gateway/
├── backend/       # Lógica de negocio y API (FastAPI)
├── ui/            # Frontend (HTML + JS + CSS)
├── migrations/    # Migraciones SQL versionadas
├── tests/         # Tests de integración y unitarios
├── scripts/       # Scripts de utilidad y administración
├── docs/          # Esta carpeta — documentación del módulo
└── data/          # Datos locales del módulo (no subir a git datos sensibles)
```

## API

Prefijo: `/api/gateway/`

Ver `backend/routers/` para los endpoints disponibles.

## Tests

```bash
pytest gateway/tests/ -v
```

## Migraciones

Ver `migrations/README.md` para instrucciones.
