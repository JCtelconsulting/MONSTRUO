# GTA — Arquitectura

Documento técnico del módulo **Gestión de Tareas Automatizadas**. Describe qué hace, qué problema resuelve, su modelo de datos y cómo se integra con el resto del stack.

## 1. Propósito

GTA reemplaza el flujo de correos internos entre áreas con un sistema de procesos guiados, ejecutables y auditables. Tres piezas centrales:

- **Catálogo de procesos**: definiciones reutilizables de qué hay que hacer, en qué orden, por qué área y con qué SLA.
- **Flujos cross-área**: instancias en ejecución de un proceso (o flujo libre) que cruzan varias áreas con tareas dependientes.
- **Semáforo SLA + escalamiento**: cada tarea tiene su propio SLA con notificaciones a 70%/85%/100% y un mecanismo de quiebres que escala a gerencia cuando algo se bloquea.

Pensado para 12 áreas operativas internas + 2 externas (prevención de riesgos, contabilidad).

## 2. Conceptos del dominio

| Concepto | Qué es |
|---|---|
| **Proceso** | Definición de un trabajo: pasos, áreas responsables, SLA, archivo de referencia. Vive en `gta.procesos`. Tiene versión que sube en cada cambio. |
| **Flujo** | Instancia ejecutable de un proceso (o flujo libre sin proceso). Agrupa tareas. Estados: `borrador`, `activo`, `completado`, `cancelado`, `vencido`. |
| **Tarea** | Un paso dentro de un flujo, asignado a un área específica. Estados: `pendiente`, `lista`, `en_progreso`, `por_validar`, `completada`, `ayuda_pedida`, `vencida`, `cancelada`. |
| **Confirmación dual** | Una tarea no se da por completada solo cuando el ejecutor la marca: pasa primero a `por_validar`, y el iniciador del flujo (o un admin) acepta o rechaza. Si rechaza, vuelve a `en_progreso`. |
| **Ayuda** | Pedido inter-área desde una tarea: "necesito que X área me responda Y para seguir". Si `bloquea_sla=true`, el SLA de la tarea se pausa hasta la respuesta. |
| **Quiebre** | Bloqueo reportado: `sin_proceso` (no existe el proceso para esto), `paso_bloqueado`, `sla_vencido`. Se cierran con `nota_resolucion` por gerencia. |
| **Dependencias** | Una tarea puede tener `depende_de: [task_ids]`. Se activa (estado `lista`) cuando todas sus dependencias están `completada`. |

## 3. Modelo de datos (schema `gta.*`)

Todas las tablas viven bajo el schema `gta` en PostgreSQL. La definición DDL está en [`plataforma/core/db.py`](../../plataforma/core/db.py) (sección `_migrate_gta_*`), no en migraciones SQL sueltas — el bootstrap se hace al arrancar el servicio.

### Tablas principales

| Tabla | Propósito |
|---|---|
| `gta.areas` | 12 áreas operativas + 2 externas. Cada una con `code`, `label`, `lider_username`, `es_externa`, `activo`, `orden`. |
| `gta.subareas` | Equipos dentro de un área (ej: `comercial → ventas`, `comercial → postventa`). FK a `areas.code`, UNIQUE `(area_code, code)`. |
| `gta.procesos` | Catálogo de procesos. Campos clave: `nombre`, `area`, `subarea_code`, `pasos_definicion` (JSON), `sla_horas`, `archivo_path`, `version`, `estado`. |
| `gta.proceso_comentarios` | Audit trail de cambios en procesos: `tipo` ∈ `nota \| cambio \| decision`. |
| `gta.flujos` | Instancias en ejecución. Campos clave: `proceso_id` (nullable, para flujos libres), `iniciado_por`, `estado`, `datos_formulario` (JSON), `sla_horas_total`. |
| `gta.flujo_tareas` | Tareas de un flujo (1 por área responsable). Campos clave: `flujo_id`, `area_code`, `subarea_code`, `asignado_a`, `depende_de` (JSON array), `sla_horas`, `estado`, `inicio_at`, `ejecutor_completo_at`, `validado_at`, `sla_paused_minutes`, `last_sla_warn_pct`. |
| `gta.flujo_ayudas` | Pedidos de ayuda inter-áreas. Campos clave: `tarea_id`, `pedido_a_area`, `bloquea_sla`, `estado` (`abierto \| respondido`), `respuesta`. |
| `gta.flujo_eventos` | Audit trail de flujos: `tipo` ∈ `iniciado \| tarea_lista \| ejecutor_completo \| validada \| rechazada \| ayuda_pedida \| ayuda_respondida \| sla_warn_70 \| sla_warn_85 \| sla_vencida \| flujo_completado`. |
| `gta.quiebres` | Bloqueos escalables a gerencia. Campos clave: `tipo`, `area`, `descripcion`, `proceso_id` (nullable), `solicitud_id` (nullable), `estado`, `nota_resolucion`. |
| `gta.settings` | Configuración global (`key TEXT PK`, `value`). Claves: `jefe_username`, `sla_warn_pct` (70), `sla_critical_pct` (85), `sla_check_interval_min` (10). |

### Tablas legacy

`gta.solicitudes` y `gta.comentarios_solicitudes` son del modelo previo (solicitudes de un solo área, sin pasos cross-área). Coexisten con flujos pero el camino nuevo es flujos. La UI sigue mostrando ambas.

### Relaciones

```
areas (code) ──< subareas (area_code)
procesos (id) ──< flujos (proceso_id)        [nullable, flujos libres no tienen proceso]
procesos (id) ──< proceso_comentarios
procesos (id) ──< quiebres (proceso_id)      [nullable]
flujos (id) ──< flujo_tareas (flujo_id)
flujos (id) ──< flujo_eventos (flujo_id)
flujo_tareas (id) ──< flujo_ayudas (tarea_id)
flujo_tareas (id) ──< flujo_tareas (depende_de [])  [array JSON, no FK]
solicitudes (id) ──< quiebres (solicitud_id) [nullable, legacy]
```

## 4. Flujo end-to-end

Ejemplo: proceso "Alta de cliente nuevo" con 3 tareas — Comercial → Sistemas → Contabilidad.

1. **Catálogo**. Admin crea el proceso en `/api/gta/procesos` con `pasos_definicion = [{area:'comercial', sla_horas:4, ...}, {area:'sistemas', depende_de:[1], ...}, {area:'contabilidad', depende_de:[2], ...}]`.
2. **Iniciar flujo**. Usuario hace `POST /api/gta/flujos {proceso_id, titulo, datos_formulario}`. El servicio crea `gta.flujos` + 3 `gta.flujo_tareas`. La tarea 1 (sin dependencias) pasa a `lista` y se setea `inicio_at=now()`. Las demás quedan `pendiente`.
3. **Ejecutar tarea 1**. El asignado de Comercial trabaja, hace `POST /flujo-tareas/{tid}/completar`. La tarea pasa a `por_validar`.
4. **Validar tarea 1**. El iniciador del flujo (o admin) hace `POST /flujo-tareas/{tid}/validar {aceptada:true}`. La tarea pasa a `completada`. El servicio busca tareas dependientes que ya tienen todas sus dependencias listas y las activa (tarea 2 pasa a `lista`).
5. **SLA tracking**. Cada 10 minutos, el job `GTA_SLA_CHECK` evalúa todas las tareas activas. Si una cruza 70%, 85% o 100% de su SLA, dispara notificación in-app + Google Chat al asignado (y al jefe en 85%/100%). A 100% marca la tarea como `vencida` y registra evento `sla_vencida`.
6. **Pedir ayuda** (opcional). Si el ejecutor de tarea 2 necesita info, `POST /flujo-tareas/{tid}/ayuda {pedido_a_area:'comercial', mensaje:'...', bloquea_sla:true}`. Tarea pasa a `ayuda_pedida` y el SLA se pausa (acumula `sla_paused_minutes`). Cuando responden con `POST /flujo-ayudas/{aid}/responder`, el SLA se reanuda.
7. **Completar**. Cuando todas las tareas están `completada`, el flujo pasa a `completado` y se loguea evento `flujo_completado`.
8. **Quiebre** (camino paralelo). Si algo se bloquea, cualquier usuario hace `POST /procesos/{pid}/quiebres {tipo:'paso_bloqueado', descripcion}`. Queda en `gta.quiebres.estado='abierto'` hasta que un admin lo resuelve (`POST /quiebres/{qid}/resolver {nota}`).

Ver [API.md](API.md) para detalle de cada endpoint.

## 5. Componentes del backend

```
gta/backend/
├── main.py                     # FastAPI app, init_db(), arranque del worker de jobs
├── router.py                   # Endpoints /api/gta/* (todo el routing)
├── services/
│   ├── catalogo.py             # Escaneo de gta/data/procesos/ (archivos en disco)
│   ├── procesos.py             # CRUD de procesos + comentarios + quiebres + seed desde archivos
│   └── flujos.py               # Orquestación de flujos: crear, completar, validar, ayudas, métricas, cálculo de SLA
└── jobs/
    └── sla_check.py            # Job recurrente cada 10 min: evalúa SLA, notifica, marca vencidas
```

**Servicios (resumen):**

- `services/catalogo.py` (2 funciones): `scan_catalog()` lee `gta/data/procesos/` y devuelve un índice jerárquico por área→subárea. `resolve_safe_path()` valida paths (anti path-traversal) para descargas.
- `services/procesos.py` (8 funciones públicas): listar/get/crear/actualizar procesos, agregar comentarios, reportar quiebres, sembrar procesos desde archivos en disco, guardar archivos subidos.
- `services/flujos.py` (10 funciones públicas): crear flujo, marcar ejecutor completo, validar tarea (aceptar/rechazar), pedir/responder ayuda, get flujo con SLA calculado, listar flujos con visibilidad RBAC, eventos, métricas globales, cálculo SLA, log de eventos.

**Job:**

- `jobs/sla_check.py` (`GTA_SLA_CHECK`): cada 10 min, evalúa tareas con estado ∈ `{lista, en_progreso, por_validar}`, no pausadas. Notifica a 70% (INFO al asignado), 85% (WARNING al asignado + jefe), 100% (CRITICAL + marca `vencida`). Usa `core.sys_notifications` y Google Chat DM si hay token disponible.

## 6. Componentes del frontend

```
gta/ui/
├── gta.html                    # Shell: header + tab bar (Tablero | Procesos)
├── tablero/
│   ├── tablero.html            # Layout: filtros, KPIs, kanban
│   └── tablero.js              # Kanban de flujos por estado, modal de detalle de flujo
├── procesos/
│   ├── procesos.html           # Layout: area pills, búsqueda, lista
│   └── procesos.js             # Biblioteca unificada (catálogo + documentos + quiebres)
├── js/
│   ├── gta_api.js              # Wrapper fetch sobre /api/gta/*
│   ├── gta_main.js             # GtaCore: init, sesión, RBAC, tab loading
│   └── gta_ui.js               # Helpers de render
└── css/gta.css
```

**Pestaña Tablero:** Kanban de flujos agrupados por estado, KPIs (activos / por_validar / vencidos / completados), filtros área/estado/búsqueda. Click en flujo abre modal con tareas + acciones (completar, validar, pedir ayuda).

**Pestaña Procesos:** biblioteca unificada (`feat 5592508`). Area pills con conteo, búsqueda, agrupación por área→subárea. Click en proceso abre detalle con pasos, flujos ejecutados (últimos 50), quiebres, comentarios, métricas (tiempo real promedio vs SLA teórico). Botones de admin (crear, subir archivo, comentar, reportar quiebre) gated por `_aplicarPermisos()`.

## 7. Integración con el resto del stack

- **Auth y sesión**: GTA hereda del gateway. `GET /` valida sesión vía `deps.require_session_hybrid()` y redirige a login si no hay sesión. El frontend obtiene perfil de `/api/sesion`.
- **RBAC**: permisos `gta:read` (lectura) y `gta:write` (escritura) definidos en `plataforma/core/config.py:ROLE_PERMISSIONS`. Admin tiene ambos; gerencia y áreas operativas tienen `gta:read`. La administración de áreas/líderes (`/api/config/gta/*`) requiere `admin.settings`.
- **Gateway**: `gateway/backend/` rutea `/gta` y `/gta/{asset}` sirviendo desde `gta/ui/`, y proxea `/api/gta/*` a `http://gta:9012`. El endpoint de configuración de áreas vive en gateway, no en GTA: `gateway/backend/routers/gta_areas.py` expone `/api/config/gta/areas` y `/api/config/gta/subareas`.
- **Notificaciones**: el job SLA usa `core.sys_notifications` (in-app, badge de campanita) y opcionalmente Google Chat DM si hay `bot_token`.
- **Independencia**: GTA no se integra con ticketera, CRM, ERP, fundación o bodega a nivel de datos. Solo comparte auth, RBAC y notificaciones.

## 8. Configuración y arranque

- **Puerto**: `9012` (env `GTA_PORT`).
- **Comando**: `uvicorn gta.backend.main:app --host 0.0.0.0 --port 9012`.
- **Build**: [`gta/Dockerfile`](../Dockerfile). Servicio `gta` en [`docker-compose.yaml`](../../docker-compose.yaml).
- **Vars de entorno propias**: ninguna. Toda la config viene de `plataforma.core.config.settings`.
- **Bootstrap de datos** (al arrancar):
  - 12 áreas + 2 externas + 15 subáreas (idempotente, `ON CONFLICT DO NOTHING`) — sembradas en `_migrate_gta_areas_section()`.
  - Settings globales (`jefe_username`, umbrales SLA) — sembradas en `_migrate_gta_flujos_section()`.
  - Catálogo de procesos: **NO** se siembra automático. Se crea por API o subiendo archivos a `gta/data/procesos/<area>/<sub>/` y luego ejecutando `POST /procesos/seed-from-files`.

## 9. Estado de tests

`gta/tests/test_solicitudes.py` tiene 4 stubs sin implementar (todos con `pass`). **Cobertura efectiva: 0%**. Pendiente cubrir: creación de flujos con dependencias, confirmación dual, pausa/reanudación de SLA con ayudas, cálculo de color SLA, RBAC en listados, job SLA en sus tres umbrales.

## 10. Pendientes / deuda observable

- **Cancelación de flujos por UI**: el estado `cancelado` existe pero no hay endpoint ni botón para cancelar.
- **Edición de flujos en ejecución**: una vez creado, el flujo es inmutable (no se pueden cambiar tareas, agregar pasos, re-asignar).
- **Re-asignación de tarea**: no hay endpoint para cambiar `asignado_a` después de creada.
- **Descarga de documentos en UI**: `GET /catalogo/download` está implementado pero la UI unificó esa pestaña en Procesos sin un botón de descarga visible.
- **Sincronización con Google Drive**: `gta/data/procesos/` se asume poblado manualmente. No hay job que sincronice desde Drive.
- **Reportes históricos de SLA**: `GET /metricas` da snapshot actual; no hay persistencia ni dashboard histórico.
- **Workflow condicional / branching**: las dependencias son secuenciales puras. No hay branching basado en resultado de un paso.
- **Tests reales**: 0% de cobertura, todo en stubs.
