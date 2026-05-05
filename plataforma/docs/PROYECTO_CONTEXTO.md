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

Estado PROD (verificado 2026-05-05 vía SSH a la VM proxy): el proxy `192.168.60.6` ya enruta a `192.168.60.5:9001` (gateway/login/config), `:9005` (ticketera api) y `:9006` (fundación api). La migración desde el modelo viejo `:9000` ya está consumada del lado proxy. Pendiente solo confirmar caso por caso que las apps en `192.168.60.5` escuchen efectivamente en esos puertos y que los binds de Postgres sigan canónicos.

## Últimos cambios

Ver bitácora completa en [changelog/](changelog/).

- **2026-05-05** — Auditoría docs vs realidad. Sincronización byte a byte de `plataforma/ops/nginx/` con la VM proxy (`monstruo.conf`/`terreneitor.conf` actualizados, `ultron.conf` agregado al repo). Borrado `plataforma/ops/guardian/` entero (sin uso real), borrados scripts Windows legacy y `pmo_v1.sql.txt`. `ARQUITECTURA.md` y `PROXY_INVERSO.md` reescritos con la realidad confirmada (PROD ya en `9001/9005/9006`, refactor `core/` ya hecho). `deploy/README.md` → `GUIA_DEPLOY.md`.
- **2026-05-04** — Cierre completo de la deuda Jira en backend (Commit B post-reorg docs).
- **2026-05-04** — Reorganización documental completa de `plataforma/docs/` por función + cambio de prioridad a GTA.

## Pendientes relevantes

- alinear tests legacy de Ticketera al árbol actual del repositorio
- terminar de converger apps incompletas o dispersas como `ia`, `pmo` y `zabbix`
