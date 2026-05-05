# GTA — Documentación

**Gestión de Tareas Automatizadas** — motor de procesos guiados entre áreas con SLA semáforo, confirmación dual y escalamiento de quiebres a gerencia. Reemplaza el flujo de correos internos.

> **Prioridad actual** del proyecto Monstruo (ver [PROYECTO_CONTEXTO.md](../../plataforma/docs/PROYECTO_CONTEXTO.md)).

## Índice de docs

- **[ARQUITECTURA.md](ARQUITECTURA.md)** — qué hace GTA, modelo de datos (`gta.*`), flujo end-to-end, componentes backend/frontend, integración con el resto del stack, pendientes visibles.
- **[API.md](API.md)** — referencia de endpoints `/api/gta/*` agrupados por dominio (procesos, áreas, flujos, tareas, quiebres, métricas, legacy).

## Arranque rápido

```bash
# Levantar el servicio (puerto interno 9012)
docker compose up gta --build

# Acceder por gateway
# https://login.telconsulting.cl/dev/gta
```

GTA hereda autenticación del gateway. No hay seed manual de áreas — se crean al arrancar (12 operativas + 2 externas). Para sembrar el catálogo de procesos, subir archivos a `gta/data/procesos/<area>/<sub>/` y ejecutar `POST /api/gta/procesos/seed-from-files` (admin).

## Estructura del módulo

```
gta/
├── backend/        # FastAPI app, router, services, jobs (SLA check)
├── ui/             # Shell + 2 pestañas (Tablero kanban, Procesos biblioteca)
├── migrations/     # SQL versionado (DDL principal vive en plataforma/core/db.py)
├── tests/          # 0% cobertura, solo stubs por ahora
├── scripts/        # Utilidades de admin
├── docs/           # Esta carpeta
└── data/           # Catálogo de procesos en filesystem (no versionado)
```

## Roles y permisos

- `gta:read` — listar/ver procesos, flujos, áreas, métricas.
- `gta:write` — crear/editar procesos, iniciar flujos, completar/validar tareas, pedir/responder ayudas, resolver quiebres.
- `admin.settings` — sembrar procesos desde archivos, administrar áreas/líderes (este último vive en `gateway/backend/routers/gta_areas.py`).

## Conceptos en una línea

- **Proceso**: receta reutilizable (pasos, áreas, SLA). Vive en `gta.procesos`.
- **Flujo**: instancia ejecutable de un proceso (o flujo libre). Vive en `gta.flujos`.
- **Tarea**: un paso del flujo, asignado a un área. Vive en `gta.flujo_tareas`.
- **Confirmación dual**: ejecutor marca → iniciador valida. Sin atajos.
- **Ayuda**: pedido inter-área que opcionalmente pausa el SLA.
- **Quiebre**: bloqueo escalable a gerencia.
- **SLA semáforo**: amarillo 70% → naranja 85% → rojo 100% (vencida). Job cada 10 min.
