# Zabbix — Monitoreo de Infraestructura

Módulo proxy hacia el servidor Zabbix externo. Expone métricas e incidentes de infraestructura dentro de la plataforma Monstruo.

## Estructura

```
zabbix/
├── backend/       # Proxy FastAPI hacia API Zabbix
├── ui/            # Dashboard de monitoreo
├── migrations/    # Migraciones SQL del schema zabbix.*
├── tests/         # Tests de integración
├── scripts/       # Scripts de utilidad
├── docs/          # Documentación del módulo
└── data/          # Datos locales (excluidos de git)
```

## Desarrollo

Módulo en etapa inicial. Ver `docs/README.md` para estado actual.
