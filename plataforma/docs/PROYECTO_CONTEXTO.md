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

## Hitos recientes

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
