# Monstruo DEV

Repositorio de desarrollo de Monstruo para Telconsulting.

## Qué hay aquí

- apps y módulos del stack Monstruo en entorno DEV
- plataforma compartida en `plataforma/`
- documentación operativa y técnica en `plataforma/docs/`

## Prioridad actual

**GTA** (Gestión y Tableros por Área). Ticketera ya en producción y mantención post-PROD.

## Documentación principal

- [Índice de docs](plataforma/docs/README.md)
- [Reglas operativas (AGENTS)](plataforma/docs/AGENTS.md)
- [Proyecto Contexto](plataforma/docs/PROYECTO_CONTEXTO.md)
- [Guía Maestra](plataforma/docs/GUIA_MAESTRA.md)
- [Arquitectura](plataforma/docs/arquitectura/ARQUITECTURA.md)
- [Proxy Inverso](plataforma/docs/arquitectura/PROXY_INVERSO.md)
- [Design System](plataforma/docs/estandares/DESIGN_SYSTEM.md)
- [Changelog](plataforma/docs/changelog/)

## Estructura corta

- `plataforma/`: base compartida, operación, docs y datos
- `gta/`: app prioridad actual
- `ticketera/`, `crm/`, `erp/`, `bodega/`, `fundacion/`, `gateway/`: apps en operación o mantención
- `CLAUDE.md`: puntero para Claude Code → reglas en `plataforma/docs/AGENTS.md`
- `plataforma/docs/AGENTS.md`: reglas operativas canónicas para todos los agentes
