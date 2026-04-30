# Zabbix — Documentación

Monitoreo de infraestructura. Proxy hacia el servidor Zabbix externo.

## Estructura

```
zabbix/
├── backend/       # Lógica de negocio y API (FastAPI)
├── ui/            # Frontend (HTML + JS + CSS)
├── migrations/    # Migraciones SQL versionadas
├── tests/         # Tests de integración y unitarios
├── scripts/       # Scripts de utilidad y administración
├── docs/          # Esta carpeta — documentación del módulo
└── data/          # Datos locales del módulo (no subir a git datos sensibles)
```

## API

Prefijo: `/api/zabbix/`

Ver `backend/router.py` para los endpoints disponibles.

## Tests

```bash
pytest zabbix/tests/ -v
```

## Migraciones

Ver `migrations/README.md` para instrucciones.
