# Documentación

Documentación viva del proyecto. Organizada por **función** para que sea fácil encontrar lo que se busca.

## Documentos principales

- [AGENTS.md](AGENTS.md) — reglas obligatorias para todo agente que toque este repo
- [PROYECTO_CONTEXTO.md](PROYECTO_CONTEXTO.md) — estado actual, prioridad vigente, decisiones
- [GUIA_MAESTRA.md](GUIA_MAESTRA.md) — guía oficial de construcción (visión, módulos, contratos)

## Arquitectura

- [arquitectura/ARQUITECTURA.md](arquitectura/ARQUITECTURA.md)
- [arquitectura/CONTRATO_APPS.md](arquitectura/CONTRATO_APPS.md) — contrato que toda app debe cumplir
- [arquitectura/FLUJO_REQUEST.md](arquitectura/FLUJO_REQUEST.md)
- [arquitectura/PROXY_INVERSO.md](arquitectura/PROXY_INVERSO.md)

## Estándares

- [estandares/ESTANDARES.md](estandares/ESTANDARES.md) — convenciones de código, UI y operación
- [estandares/DESIGN_SYSTEM.md](estandares/DESIGN_SYSTEM.md) — sistema de diseño (paleta, tipografía, componentes)

## Operación y despliegue

- [operacion/deploy/](operacion/deploy/) — scripts y plantillas de deploy
- [operacion/playbooks/](operacion/playbooks/) — playbooks de validación y troubleshooting
- [operacion/windows/](operacion/windows/) — accesos directos para clientes Windows

## Recursos técnicos

- [recursos/apis/](recursos/apis/) — especificaciones OpenAPI de integraciones
- [recursos/sql/](recursos/sql/) — scripts SQL de referencia

## Demo y comercial

- [demo/](demo/) — guion, escenarios y KPIs para demos comerciales

## Histórico

- [changelog/](changelog/) — bitácora del proyecto, partida por mes-año
- [archive/](archive/) — documentos archivados (no operativos)

## Documentación específica por app

Cada app mantiene su propia documentación operativa en `app/docs/`:

- [ticketera/docs/](../../ticketera/docs/) — en mantención post-PROD
- [gta/docs/](../../gta/docs/) — **prioridad actual** ([Arquitectura](../../gta/docs/ARQUITECTURA.md) · [API](../../gta/docs/API.md))
- [crm/docs/](../../crm/docs/)
- [erp/docs/](../../erp/docs/)
- [bodega/docs/](../../bodega/docs/)
- [fundacion/docs/](../../fundacion/docs/)
- [gateway/docs/](../../gateway/docs/)

## Regla

La documentación viva del proyecto debe quedar en `plataforma/docs/`.

La raíz del repo queda reservada para:

- `README.md`
- `CLAUDE.md` (puntero a `plataforma/docs/AGENTS.md`)

`AGENTS.md` vive en `plataforma/docs/` junto al resto de la documentación canónica. No se deben volver a dejar documentos operativos largos en la raíz.
