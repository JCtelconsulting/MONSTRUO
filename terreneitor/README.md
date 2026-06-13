# Terreneitor

Sistema de Gestión Operativa (Libro de Obras Digital). Desde 2026-06-12 vive como
**módulo del ecosistema Monstruo** (monorepo). Estado del módulo: [ESTADO.md](ESTADO.md).

## 🚀 Inicio Rápido

Terreneitor corre como un servicio más del **compose único** del repo Monstruo
(ya no tiene compose propio). Desde la raíz del repo:

```bash
# Levantar todo el stack (incluye terreneitor en el puerto 8005):
docker compose --env-file plataforma/ops/env/.env.server.dev up -d --build

# Rebuild solo de terreneitor (maneja ASSET_VERSION para cache-busting):
./plataforma/ops/scripts/dev-rebuild.sh terreneitor
```

La app queda en `terreneitor.telconsulting.cl/dev` (vía proxy) o en el puerto
`8005` del host DEV.

## 📚 Documentación
- **[MIGRACION_MONSTRUO.md](docs/MIGRACION_MONSTRUO.md)**: cómo pasó a ser módulo de Monstruo (el doc clave).
- **[PROYECTO_CONTEXTO.md](docs/PROYECTO_CONTEXTO.md)** · **[PLAN_MAESTRO.md](docs/PLAN_MAESTRO.md)**: bitácora histórica del proyecto standalone.
- **[HANDOVER_TECNICO.md](docs/HANDOVER_TECNICO.md)**: guía para desarrolladores y mantenimiento.

### Manuales de Usuario
- [Manual Terreno](docs/manuales/usuario_terreno.md)
- [Manual Supervisor](docs/manuales/usuario_supervisor.md)
- [Manual Gerencia](docs/manuales/usuario_gerencia.md)
- [Manual Portal/Admin](docs/manuales/usuario_portal.md)

## 📂 Organización del Proyecto (layout de módulo Monstruo)
*   **`backend/`**: Backend FastAPI (`core/`, `models/`, `services/`, `api/`, `utils/`). Entry: `backend/main.py`.
*   **`ui/`**: Frontend modular (`modulos/` + `_compartido/`).
*   **`scripts/`**: Automatización (backup, QA, mantenimiento, migración).
*   **`tests/`**: `unit/` (pytest) + `e2e/` (Playwright).
*   **`migrations/`** + `alembic.ini`: migraciones Alembic.
*   **`environments/`**: `.env.example` del módulo (el `.env` real va gitignored).
*   **`data/`** · **`logs/`**: volúmenes locales del contenedor (los datos viven en Postgres central, schema `terreneitor`).
*   **`docs/`**: documentación técnica.
*   **`Dockerfile`** · **`requirements.txt`** · **`__init__.py`**: imagen y paquete del módulo (los usa el compose único raíz).
