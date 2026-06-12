# GTA — Referencia API

Endpoints del módulo Gestión de Tareas Automatizadas. Prefijo: `/api/gta/`.

> **Nota de auth**: todos los endpoints requieren sesión válida (heredada del gateway) y un permiso explícito declarado en cada uno (`gta:read`, `gta:write`, `admin.settings`). Sin sesión → 401. Sin permiso → 403.

## Convenciones

- Códigos: `200` OK por defecto, `400` validación, `401`/`403` auth, `404` no existe, `409` conflicto de estado.
- Cuerpos JSON salvo donde se indique `multipart/form-data`.
- Fechas en formato ISO 8601 UTC.
- Visibilidad de listados: admin ve todo. Líder de área ve flujos de su área. Usuario común ve solo lo que inició o lo asignado.

---

## Procesos (catálogo)

### `GET /procesos`
Lista de procesos del catálogo. Permiso: `gta:read`.

Query params: `estado` (default `activo`), `area`, `subarea`, `busqueda`.

Retorna: `{items: [{id, nombre, area, subarea_code, descripcion, sla_horas, icono, estado, version, flujos_count, quiebres_count, quiebres_abiertos, ...}]}`

### `GET /procesos/{pid}`
Detalle de un proceso con flujos ejecutados (últimos 50), quiebres, comentarios y métricas. Permiso: `gta:read`.

Retorna: `{id, nombre, ..., pasos_definicion, campos_formulario, flujos: [...], quiebres: [...], comentarios: [...], metricas: {prom_horas_real, sla_teorico, ...}}`

### `POST /procesos`
Crea un proceso en el catálogo. Permiso: `gta:write`.

Body: `{nombre*, area*, descripcion, sla_horas, icono, pasos_definicion (JSON string), campos_formulario (JSON string)}`. El `sla_horas` total se recalcula sumando los pasos si vienen pasos.

### `PUT /procesos/{pid}`
Actualiza un proceso. Cualquier cambio incrementa `version` y registra un comentario tipo `cambio`. Permiso: `gta:write`.

### `POST /procesos/{pid}/comentarios`
Agrega comentario al audit trail del proceso. Permiso: `gta:write`.

Body: `{texto*, tipo}` — tipo ∈ `nota | cambio | decision` (default `nota`).

### `POST /procesos/{pid}/quiebres`
Reporta un quiebre asociado a este proceso. Permiso: `gta:write`.

Body: `{descripcion*, area*, tipo}` — tipo ∈ `sin_proceso | paso_bloqueado | sla_vencido`.

### `POST /procesos/{pid}/archivo`
Sube un archivo de referencia (manual, plantilla) y lo vincula al proceso (`archivo_path`). Permiso: `gta:write`.

Cuerpo: `multipart/form-data` con campo `file`. Se guarda en `gta/data/procesos/<area>/<sub>/<filename>`.

### `POST /procesos/seed-from-files`
Escanea `gta/data/procesos/` y crea registros en `gta.procesos` para cada archivo no registrado. Idempotente. Permiso: `admin.settings`.

Retorna: `{creados, omitidos, total_archivos}`.

---

## Áreas

### `GET /areas`
Lista pública de áreas y subáreas activas. Permiso: `gta:read`. Usado por la UI para llenar selects.

Retorna: `{items: [{code, label, lider_username, lider_nombre, es_externa, activo, orden, subareas: [{code, label, lider_username, ...}]}]}`

> Para administración (PUT/POST de áreas y subáreas), ver endpoints en gateway: `/api/config/gta/areas` (requiere `admin.settings`).

---

## Catálogo de documentos (filesystem)

### `GET /catalogo`
Índice del filesystem en `gta/data/procesos/`. Permiso: `gta:read`.

Retorna estructura jerárquica: `{areas: [{code, files: [...], subareas: [{code, files: [...]}]}], sueltos: [...], total_procesos, scanned_at, missing_root?}`.

### `GET /catalogo/download?path=<rel>`
Descarga un archivo del catálogo. Permiso: `gta:read`. El `path` se valida contra path-traversal.

Retorna: `FileResponse`.

---

## Flujos (cross-área)

### `POST /flujos`
Crea un flujo en ejecución. Permiso: `gta:write`.

Body: `{titulo*, descripcion, proceso_id, datos_formulario, pasos_libres}`. Pasar **uno** de `proceso_id` (instancia desde catálogo) o `pasos_libres` (flujo libre sin catálogo).

Comportamiento: crea el flujo y todas sus tareas. Tareas sin dependencias quedan en `lista` con `inicio_at=now()`. El resto queda en `pendiente`. Loguea evento `iniciado`.

### `GET /flujos`
Lista de flujos con filtro RBAC automático. Permiso: `gta:read`.

Query params: `estado`, `area`, `limit=100`, `offset=0`.

Retorna: `{items: [...], total}`. Visibilidad: admin → todo, líder → su área, usuario → lo suyo.

### `GET /flujos/{fid}`
Detalle de un flujo con tareas serializadas (incluyendo cálculo de SLA por tarea) y resumen agregado. Permiso: `gta:read`.

Retorna: `{id, titulo, estado, ..., tareas: [{id, titulo, area_code, asignado_a, estado, sla_horas, sla: {pct, color, vencida, esta_pausada, minutos_consumidos, minutos_total, minutos_pausados}, ...}], resumen: {total_tareas, completadas, vencidas, pct_completado}}`

Colores SLA: `gray` (sin iniciar), `green` (completada <100%), `rojo_completado` (completada ≥100%), `blue` (por_validar), `cyan` (lista/en_progreso <70%), `yellow` (70-85%), `orange` (85-100%), `red` (≥100%), `purple` (ayuda_pedida).

### `GET /flujos/{fid}/eventos`
Audit trail del flujo (últimos N eventos, default 100). Permiso: `gta:read`.

Retorna: `[{tipo, actor, mensaje, metadata, created_at}]` ordenado DESC.

---

## Tareas de flujos

### `POST /flujo-tareas/{tid}/completar`
El ejecutor marca la tarea como hecha. Permiso: `gta:write`.

Body: `{campos_completados}` (opcional, key/value de campos requeridos).

Resultado: tarea pasa a `por_validar`. Si estaba pausada por ayuda, se reanuda el SLA acumulando el tiempo pausado.

### `POST /flujo-tareas/{tid}/validar`
Confirmación dual. Solo el iniciador del flujo o un admin puede validar. Permiso: `gta:write`.

Body: `{aceptada* (bool), comentario}`.

Resultado:
- `aceptada=true`: tarea → `completada`. Activa tareas dependientes que ya tienen todas sus dependencias listas. Si era la última, cierra el flujo (`flujo_completado`).
- `aceptada=false`: tarea vuelve a `en_progreso`. Loguea evento `rechazada` con el comentario.

### `POST /flujo-tareas/{tid}/ayuda`
Pide ayuda a otra área desde una tarea. Permiso: `gta:write`.

Body: `{pedido_a_area*, pedido_a_user, mensaje*, bloquea_sla (bool)}`.

Si `bloquea_sla=true`: tarea pasa a `ayuda_pedida` y se inicia pausa de SLA (`sla_pause_started_at=now()`).

### `POST /flujo-ayudas/{aid}/responder`
Respuesta a un pedido de ayuda. Permiso: `gta:write`.

Body: `{respuesta*}`.

Resultado: ayuda → `respondido`. Si bloqueaba SLA, tarea vuelve a `en_progreso` y se acumula el tiempo de pausa en `sla_paused_minutes`.

---

## Quiebres

### `GET /quiebres`
Lista quiebres con filtros. Permiso: `gta:read`.

Query: `estado=abierto`, `area`, `tipo`.

### `POST /quiebres`
Crea un quiebre suelto (no asociado a proceso vía URL). Permiso: `gta:read`. Audita evento `GTA_CREATE_QUIEBRE` (severity warning).

Body: `{descripcion*, area*, tipo, solicitud_id}`.

### `POST /quiebres/{qid}/resolver`
Cierra un quiebre. Permiso: `gta:write`. Audita `GTA_RESOLVER_QUIEBRE` (severity info).

Body: `{nota}`.

---

## Estadísticas

### `GET /stats`
Snapshot rápido para el header del tablero. Permiso: `gta:read`.

Retorna: `{pendientes, en_progreso, completadas, completadas_hoy, bloqueadas, total, quiebres_abiertos}`.

### `GET /metricas`
Agregados por persona y por área. Permiso: `gta:read`.

Retorna: `{totales: {activos, completados, vencidos, total}, por_persona: [{persona, completadas, activas, vencidas, prom_min}], por_area: [{area, completadas, activas, vencidas}]}`.

---

## Solicitudes (legacy)

Modelo previo a flujos: una solicitud = un proceso de un área, sin pasos cross-área. Coexiste con flujos. Endpoints: `GET /solicitudes`, `GET /solicitudes/{sid}`, `POST /solicitudes`, `PATCH /solicitudes/{sid}`, `POST /solicitudes/{sid}/pasos/{idx}/completar`, `POST /solicitudes/{sid}/pasos/{idx}/bloquear`, `GET/POST /solicitudes/{sid}/comentarios`.

Todos requieren `gta:read`. Filtros de visibilidad RBAC iguales que en flujos.

---

## Configuración (en gateway, no en GTA)

Estos endpoints viven en `gateway/backend/routers/gta_areas.py` y requieren `admin.settings`:

- `GET /api/config/gta/areas` — lista para administración (incluye inactivas).
- `PUT /api/config/gta/areas/{code}` — actualiza líder, label, estado, orden.
- `POST /api/config/gta/subareas` — crea subárea.
- (otros CRUD de subáreas según código del gateway).
