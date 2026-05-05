# Proyecto Contexto

## Estado operativo actual

- entorno de trabajo: `dev`
- prioridad actual: **GTA** (Gestión y Tableros por Área)
- ticketera: en producción y mantención post-PROD (EPIC 11 cerrado)
- objetivo vigente: avanzar GTA sin romper DEV/PROD ni regresar a la ticketera salvo bug crítico

## Estructura canónica vigente

- raíz del repo:
  - `README.md`
  - `CLAUDE.md` (puntero a `plataforma/docs/AGENTS.md`)
- documentación viva:
  - `plataforma/docs/` (incluye `AGENTS.md` canónico)
- operación y despliegue:
  - `plataforma/ops/`
- proxy versionado:
  - `plataforma/ops/nginx/`

## Proxy inverso

VM proxy actual:

- `192.168.60.6`

Configuración activa versionada:

- `plataforma/ops/nginx/monstruo.conf`
- `plataforma/ops/nginx/terreneitor.conf`
- `plataforma/ops/nginx/sapa.conf`

Estado funcional resumido:

- `Monstruo` unificado
- `Terreneitor` unificado
- `Sapa` separado
- `Ultron` eliminado del árbol activo

## Modelo actual por entorno

`PROD`:

- Monstruo funciona hoy como monolito para `ticketera`, `login` y `config`
- publicación pública por `/`

`DEV`:

- se está separando por servicios reales
- publicación pública por `/dev/`
- no se debe heredar backend de otra app por arrastre histórico

## Decisiones vigentes

- el proxy real debe mantenerse sincronizado con `plataforma/ops/nginx/`
- no se dejan documentos largos en la raíz
- `PROD` y `DEV` se separan por configuración y contratos, no por improvisación
- una app nueva debe seguir un patrón definido en `CONTRATO_APPS.md`

## Contrato canónico de compose DEV/PROD

`docker-compose.yaml` en raíz es ahora un único contrato parametrizable que aplica idéntico en DEV y PROD. Reglas no negociables (validadas por `plataforma/tests/ci_repo_guard.py`):

- Postgres NUNCA publica `5432` al host. La DB sólo es accesible por la red interna de docker.
- Gateway publica `${GATEWAY_PORT:-9001}:9001`. Ticketera publica `${TICKETERA_PORT:-9005}:9005`.
- Datos Postgres persisten como bind mount `./plataforma/data/postgres:/var/lib/postgresql/data` (idéntico DEV/PROD).
- Adjuntos persisten como bind mount `./plataforma/data_runtime/{tickets,compliance}` en gateway y ticketera.
- `env_file` se resuelve por `${ENV_FILE:-plataforma/ops/env/.env.server.dev}`.
- `container_name` se deriva de `${STACK_NAME:-monstruo-dev}` (`monstruo-dev-*` en DEV, `monstruo-*` en PROD).

Variables canónicas por entorno:

- DEV: `STACK_NAME=monstruo-dev`, `POSTGRES_DB=monstruo_dev`, `ENV_FILE=plataforma/ops/env/.env.server.dev`
- PROD: `STACK_NAME=monstruo`, `POSTGRES_DB=monstruo`, `ENV_FILE=plataforma/ops/env/.env.server`

Migración PROD pendiente (ventana controlada con backup `pg_dump` previo): mover datos Postgres al bind `/srv/monstruo/plataforma/data/postgres`, exponer gateway en `9001` y ticketera en `9005`, ajustar `plataforma/ops/nginx/monstruo.conf` para `9001`/`9005`, actualizar `HEALTH_URL` en `.github/workflows/deploy.yml` a `9001`.

## Últimos cambios

Ver bitácora completa en [changelog/](changelog/).

- **2026-05-04** — Cierre completo de la deuda Jira en backend (Commit B post-reorg docs).
- **2026-05-04** — Reorganización documental completa de `plataforma/docs/` por función + cambio de prioridad a GTA.
- **2026-04-29** — `docker-compose.yaml` queda como contrato canónico único DEV/PROD parametrizado.

## Pendientes relevantes

- alinear tests legacy de Ticketera al árbol actual del repositorio
- terminar de converger apps incompletas o dispersas como `ia`, `pmo` y `zabbix`
