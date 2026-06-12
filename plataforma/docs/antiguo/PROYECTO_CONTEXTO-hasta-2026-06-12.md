# Proyecto Contexto

## Estado operativo actual

- entorno de trabajo: `dev`
- prioridad absoluta: `EPIC 11 / Ticketera`
- objetivo vigente: ordenar la base técnica sin mezclar `DEV` y `PROD`

## Estructura canónica vigente

- raíz del repo:
  - `README.md`
  - `AGENTS.md`
- documentación viva:
  - `plataforma/docs/`
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

## Hitos recientes

- 2026-04-29: `docker-compose.yaml` queda como contrato canónico único DEV/PROD parametrizado por `STACK_NAME`/`ENV_FILE`/`POSTGRES_DB`/`GATEWAY_PORT`/`TICKETERA_PORT`. Postgres no publica `5432`, persiste como bind `./plataforma/data/postgres` (preservando datos DEV existentes), gateway publica `9001`, ticketera publica `9005`, mounts críticos de adjuntos en `./plataforma/data_runtime/{tickets,compliance}`. Se extiende `plataforma/tests/ci_repo_guard.py` con guardas anti-regresión (prohíbe publicar `5432`, exige puertos `9001`/`9005`, bind Postgres canónico, mounts `data_runtime` y parametrización `ENV_FILE`/`STACK_NAME`). `python3 plataforma/tests/ci_repo_guard.py` → `PASS`. `docker compose --env-file plataforma/ops/env/.env.server.dev config` → válido sin warnings. Estado: contrato listo en DEV; migración PROD queda condicionada a ventana con backup + ajuste nginx + health URL.

- 2026-04-28: Saneamiento canónico ejecutado en PROD (`192.168.60.5 / TERRENEITOR`) vía SSH sin sudo (árbol `/srv/monstruo` propiedad de `juan:juan`). Se creó `/srv/monstruo/plataforma/ops/env/` y se copió `.env.server` desde la fuente legacy `/srv/monstruo/ops/env/.env.server` (más reciente, 1580B). Evidencia: `src_sha=dst_sha=c707b960467bfc8f2f0e40c12462e3c48ff0999b8cef768a92bd202d3d6aa676` (PASS hashes coinciden), destino con `size=1580 perms=600 owner=juan:juan`, contenedores `monstruo-gateway`, `monstruo-ticketera` y `monstruo-postgres` siguen `Up 2 weeks` sin reinicio. Ruta canónica AGENTS.md §4 ahora disponible para que `deploy.yml` y `deploy.sh` la encuentren al promover. Estado operativo: **GO condicional** para `dev -> main`, pendiente autorización explícita del usuario (AGENTS.md §4 + §9).
- 2026-04-27: CI deploy alineado a ruta canónica AGENTS.md §4: `.github/workflows/deploy.yml` ahora exporta `env_file=/srv/monstruo/plataforma/ops/env/.env.server` para `branch=main` (commit `c1c5498` en `dev`). Auditoría read-only en PROD (`192.168.60.5 / TERRENEITOR`) confirma que la ruta canónica todavía no existe en PROD (solo árbol legacy `/srv/monstruo/.env.server` y `/srv/monstruo/ops/env/.env.server`); decisión adoptada: **Opción B** — mantener fix canónico y sanear PROD en ventana controlada (mkdir `plataforma/ops/env` + copia de `.env.server`) antes de promover `dev -> main`.
- 2026-04-27: PROD genera respaldo fresco pre-promoción en `/home/juan/monstruo_old/pre_promote_20260427_193319`. Evidencia validada: `monstruo_db.dump` (2.0M, header `PGDMP`, 750 TOC entries, dbname=`monstruo`, `pg_dump.err` vacío), `monstruo_fs.tgz` (15M, `gzip -t` OK, 294 entradas, `tar.err` vacío), copias separadas `.env.server.root.bak` y `.env.server.opsenv.bak` con permisos `0600`, y `SHA256SUMS` calculado para los cuatro artefactos. Estado operativo: **NO-GO** para `dev -> main` se mantiene hasta completar saneamiento canónico en PROD y ensayo en staging.
- 2026-04-27: PROD completa respaldo pre-saneamiento en ruta externa con permisos (`/home/juan/monstruo_old/pre_saneamiento_20260427_144329`) tras bloqueo por permisos en `/srv/monstruo_old`. Evidencia validada: `monstruo_db.dump` y `monstruo_fs.tgz` con `SHA256SUMS` en verde, `gzip` OK del tar, lectura de contenido del tar OK y encabezado `PGDMP` del dump PostgreSQL. Estado operativo: **NO-GO** para promover `dev -> main` hasta ejecutar saneamiento controlado de árbol runtime en PROD.
- 2026-04-27: Fundación en DEV queda canónica fuera de `gateway/frontend/fundacion`: el frontend (`fundacion.html` + `js/fundacion.js`) se mueve a `fundacion/ui/`, `gateway` deja de servir archivos legacy y pasa a resolver `/fundacion` desde la ubicación canónica, con guarda CI en `plataforma/tests/ci_repo_guard.py` para bloquear regresión de esa ruta antigua.
- 2026-04-27: DEV elimina accesos directos estructurales para reforzar separación modular: se quita `.env` en raíz (obligando resolución por `ENV_FILE` y `plataforma/ops/env/.env.server.dev` en DEV), se eliminan `bodega/core`, `crm/core`, `erp/core` y `fundacion/core` (ya no hay `core` espejo por app), y se migran imports de apps activas y scripts operativos a `plataforma.core` explícito. Se mantiene `ticketera/data/*` como enlace transicional hacia `plataforma/data_runtime/*` por continuidad runtime.
- 2026-04-23: Fundación en DEV completa ajuste UX/operación en selector y administración: cada sede muestra solo nombre + encargado visible; el encargado se resuelve automáticamente por rol (`encargado_*`) según usuarios activos; y se habilita gestión embebida de usuarios/roles Fundación (crear, editar, activar/desactivar y eliminar) desde el mismo módulo, consumiendo `GET/POST/PATCH/DELETE /api/admin/users` + `GET /api/config/role-scopes`, con fallback controlado ante falta de permiso `admin.settings`.
- 2026-04-23: Fundación en DEV ajusta taxonomía de cursos en selector por sede: se eliminan `Viernes Comunidad`, `Hitos y Celebraciones` y `Rutina` del catálogo visible (tratadas como actividades), manteniendo como cursos operativos solo `Prekinder y Kinder`, `1ro y 2do básico` y `3ro y 4to básico`.
- 2026-04-23: Fundación en DEV actualiza UX visible de acceso por sede: catálogo reemplazado por sedes operativas (`La Pintana`, `Maipú`, `Llay-Llay`, `Huechuraba`, `Renca`, `Lo Espejo`, `Cerro Navia`), grilla ordenada en 3 columnas y navegación inicial por acordeón de cursos (el workspace abre recién al elegir curso).
- 2026-04-23: Fundación en DEV queda con control de alcance por usuario (scope sede/curso) de punta a punta: se agrega `fundacion_scope` al flujo de sesión (`/api/sesion`), se habilita CRUD en `admin_users` para asignar alcance, y se implementa enforcement server-side en `GET/POST/PATCH/DELETE /api/fundacion/tareas` para impedir acceso o cambios fuera de sede/curso permitido.
- 2026-04-23: Fundación en DEV normaliza estructura de datos de planificación: migración incremental agrega columnas `sede`, `curso`, `categoria`, `categoria_madre`, `subcategoria` e índices operativos en `fundacion.fundacion_tareas`, alineando backend con frontend de planificación por sede y curso.
- 2026-04-22: Fundación en DEV recibe Hito 1 UX para transformación digital: selector de 7 sedes a nivel nacional, navegación por sede y vista interna con tabs `Planificación | Inventario | Reportes`, incluyendo calendario día/semana/mes estilo operativo y paneles base de inventario/reportabilidad listos para conectar backend por sede.
- 2026-04-22: DEV habilita Fundación en dominio de login sin subdominio propio: `https://login.telconsulting.cl/dev/fundacion` queda soportado desde `gateway` con shell base en `gateway/frontend/fundacion/`, ruteo dedicado (`/fundacion` + estáticos) y navegación lateral apuntando al login central en DEV.
- 2026-04-14: se corrige el loop de `ticketera.telconsulting.cl/dev/`; `gateway` vuelve a preservar el `Host` original hacia `ticketera` y el helper de login ya considera `X-Forwarded-Host`, dejando el redirect correcto hacia `https://login.telconsulting.cl/dev/`
- 2026-04-14: se normaliza la documentación en `plataforma/docs/`
- 2026-04-14: se versiona en el repo la configuración activa del proxy inverso
- 2026-04-14: se crea una guarda de estructura (`plataforma/tests/ci_repo_guard.py`)
- 2026-04-14: la CI base deja de apuntar a rutas legacy y valida el árbol real del repo

## Pendientes relevantes

- alinear tests legacy de Ticketera al árbol actual del repositorio
- terminar de converger apps incompletas o dispersas como `ia`, `pmo` y `zabbix`
- 2026-06-12: Terreneitor entra como módulo de Monstruo en DEV (Fases 1-2). Código en `terreneitor/` (copia del repo original `/srv/terreneitor_dev`, que conserva la historia git), contenedor `monstruo-dev-terreneitor` con compose propio `terreneitor/docker-compose.yaml` (NO se tocó el compose raíz por el hotfix en curso; bloque listo para plegar en `terreneitor/docs/MIGRACION_MONSTRUO.md`). Puerto host `8005` (el proxy ya ruteaba ahí: sin cambios de nginx). Datos migrados de SQLite al Postgres central, schema `terreneitor` (script con verificación → PASS 10/10 tablas); rollback = quitar `TERRENEITOR_DATABASE_URL` del env del módulo. E2E navegador sobre Postgres: supervisor/terreno/gerencia sin errores. Pendiente: plegar al compose raíz + commit del módulo cuando aterrice `hotfix/imap-robust`, Fase 3 SSO con gateway (diseño en el doc; ojo colisión cookie `access_token` en PROD), réplica en PROD.
- 2026-06-12 (2): SSO del ecosistema en DEV — Terreneitor acepta la sesión del gateway (cookie `access_token`, validación con la SECRET_KEY del stack + autorización contra `auth.users.allowed_modules`, usuario espejo auto-provisionado). Módulo `terreneitor` registrado en `UI_MODULES`/`PERMISSION_TO_MODULE_MAP`/`sidebar.js`/`users_ui.js` (gateway reconstruido). Verificado en navegador: sesión del gateway entra a Terreneitor sin segundo login. Pendiente: asignar el módulo `terreneitor` en `allowed_modules` de los usuarios (Configuración→Usuarios); para PROD resolver colisión de cookie `access_token`. Detalle: `terreneitor/docs/MIGRACION_MONSTRUO.md`.
- 2026-06-12 (3): Terreneitor queda como módulo pleno del ecosistema en DEV — URL única `terreneitor.telconsulting.cl` (raíz redirige al HUB con tarjetas por rol; subdominios legacy portal/supervisor/gerencial/terreno → 307 a la URL única), SIN login propio (rebota a `login.telconsulting.cl`; SSO del gateway), barra del ecosistema con los módulos permitidos (`/api/sesion`). Tema Premium Gold (dorado #D4A843 sobre #050505) aplicado a la shell de Monstruo (`gateway/frontend/shared/ui/css/monstruo.css` + login del gateway) — gateway/ticketera/fundacion reconstruidos. `plataforma/ops/nginx/terreneitor.conf` (copia repo): base del host terreneitor apunta a `/modulos/hub/` (el proxy real NO necesita cambio inmediato: la app ya no sirve HTML en la raíz). Verificado E2E navegador. Commits en repo terreneitor: b2fa69a, f8831e9.
