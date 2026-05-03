# GTA — Gestión de Tareas Automatizadas

Módulo de gestión interna de procesos entre áreas. Reemplaza el flujo de correos internos con un catálogo de procesos guiados, seguimiento de pasos, SLA semáforo y escalamiento de quiebres a gerencia.

## Estructura

```
gta/
├── backend/       # Modelos Pydantic y router FastAPI
├── ui/            # Frontend: tablero kanban, catálogo, quiebres
├── migrations/    # Migraciones SQL del schema gta.*
├── tests/         # Tests de integración
├── scripts/       # Scripts de administración
├── docs/          # Documentación del módulo
└── data/          # Datos locales (excluidos de git)
```

## Levantar en dev

```bash
docker compose up gta --build
```

Puerto: `9012` — accesible vía gateway en `/gta`

## Ejecutar migración inicial

```bash
docker exec -i monstruo-dev-db psql -U monstruo -d monstruo_dev < gta/migrations/001_initial.sql
```
