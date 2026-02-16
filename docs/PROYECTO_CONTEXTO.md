# PROYECTO CONTEXTO: MONSTRUO
**Fecha de actualizacion:** 15 Febrero 2026
**Fuente de verdad:** `docs/PLAN_MAESTRO_MONSTRUO`

## HITO: 2026-02-16 11:30 - Deploy PROD: Fix PMO + Ticketera V1
- **Solicitud**: Desplegar todos los avances de desarrollo a producción (Fix PMO + Ticketera completa).
- **Entregables**:
  - **PMO**: Fix crítico en `init_db` (Postgres syntax) y `pmo.py` para creación de tablas `pmo_proyectos` y `pmo_bitacora_ia`.
  - **Ticketera**: Despliegue de todas las funcionalidades EPIC 11 (SLA, Workflow, Canales, Compliance) validadas en DEV.
- **Ops/CI-CD**: Robustecimiento de `deploy.sh` con `git checkout -f` y limpieza manual del entorno `PROD` para desbloquear el pipeline automático tras detectar cambios locales que bloqueaban el `checkout`.
- **Estado**: DESPLEGADO Y OPERATIVO.

## HITO: 2026-02-15 16:30 - EPIC 11 Estabilización Ticketera (Plan 4 semanas) implementado en DEV
- **Solicitud**: Ejecutar implementación end-to-end del plan de estabilización EPIC 11 para dejar Ticketera operativa previo paralelo Jira+MONSTRUO.
- **Entregable**:
  - Cola/worker:
    - recuperación de `RUNNING` stale robusta sin romper índices únicos en recurrentes (`EMAIL_POLLING`/`PROCESS_NOTIFICATIONS`).
    - dedupe fuerte de recurrentes con helper único `enqueue_unique_job` + índices parciales en `sys_jobs`.
    - `poll_email_job` y `process_pending_notifications` con scheduling determinista y control anti-churn (`CHANNELS_ENABLED=false` -> ciclo espaciado).
    - cleanup operativo `sys_jobs` con retención configurable (`CLEANUP_SYS_JOBS`, `SYS_JOBS_RETENTION_DAYS`).
    - endpoint operativo nuevo: `POST /api/jobs/recover-stale`.
  - API Ticketera:
    - GET críticos sin side effects en DB (`/api/tks/tickets`, `/api/tks/tickets/{id}`, `/api/tks/sla/metrics`).
    - evaluación SLA movida a job periódico `TKS_SLA_EVALUATE`.
    - endpoint operativo nuevo: `GET /api/tks/ops/queue-health`.
    - endpoint nuevo de operación real: `GET /api/tks/tickets/{ticket_id}/attachments/{attachment_id}/download`.
  - Compliance durable:
    - idempotencia de export/purge corregida para permitir rerun cuando run previo falla o falta artefacto.
    - `artifact_exists`, `artifact_verified_at` y `duplicate_skipped_reason` en responses/listados.
    - auto-reparación de cadena hash (`audit_logs`/`evidence_events`) en init cuando detecta inconsistencia.
  - Adjuntos:
    - ingestión de adjuntos entrantes por correo + persistencia con hash.
    - adjuntos de `reply-email` ahora también persisten en `ticket_attachments`.
    - naming de archivos endurecido con sufijo único para evitar colisiones por segundo.
  - UI Ticketera:
    - tab `Ops` implementado con vista mínima operativa (queue health, canales, retry, recover stale, runs Jira, KPI paralelo, compliance export).
    - descarga de adjuntos desde detalle de ticket.
  - Entorno/plantillas:
    - variables explícitas por entorno: `TICKET_ATTACHMENTS_DIR`, `COMPLIANCE_EXPORT_DIR`, `JOBS_STALE_RUNNING_MINUTES`, `SYS_JOBS_RETENTION_DAYS`, `TKS_SLA_EVAL_LIMIT`.
    - `docker-compose.yaml` actualizado con mounts persistentes para ticketera/compliance en rutas DEV/PROD esperadas del contenedor.
- **Validación ejecutada en DEV**:
  - `python3 tests/verify_hardening.py --check-api --user qa_epic11 --password '***' --timeout 60` -> PASS
  - `python3 tests/e2e_api_full.py --user qa_epic11 --password '***' --timeout 60` -> PASS
  - `python3 tests/e2e_ticketera.py --user qa_epic11 --password '***' --timeout 60` -> PASS
- **Estado**: CERRADO (implementación + validación técnica en DEV).

## HITO: 2026-02-15 08:40 - EPIC 11 Auto-Respuesta Segura v1 (allowlist + antiloop + hilo completo)
- **Solicitud**: Implementar auto-respuesta de recepción sin riesgo operacional y sin romper el flujo actual de Ticketera.
- **Entregable**:
  - Configuración nueva por entorno:
    - `TICKET_AUTO_REPLY_DELAY_MINUTES`
    - `TICKET_AUTO_REPLY_ALLOWLIST_EMAILS`
    - `TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS`
    - `TICKET_AUTO_REPLY_REQUIRE_ALLOWLIST`
    - `TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS`
  - Persistencia y threading:
    - `tickets.email_references` incorporado a creación de ticket y match por hilo.
    - `In-Reply-To`/`References` acumulados y acotados para evitar conversaciones partidas.
  - Motor de decisión:
    - evaluación determinística `enabled -> email válido -> blocklist -> allowlist -> one-shot`.
    - fail-closed por defecto (`require_allowlist=true`).
  - Programación/ejecución:
    - agenda de auto-reply con delay configurable (default 15m) e idempotencia estable por `ticket_id+destinatario`.
    - registro de trazabilidad en `ticket_emails` con direcciones `auto_reply_pending`, `auto_reply`, `auto_reply_skipped`.
    - job `SEND_AUTO_RESPONSE` endurecido con lock por ticket, dedupe final, envío avanzado con headers de hilo y actualización de metadata de thread.
  - Validación:
    - `tests/e2e_ticketera.py` extendido con bloque de auto-reply seguro (allowlist, blocklist, one-shot, thread chain).
    - `tests/verify_hardening.py` extendido para exigir variables `TICKET_AUTO_REPLY_*` en config y plantillas.
    - Validación ejecutada en DEV:
      - `python3 tests/verify_hardening.py` PASS
      - Smoke técnico en contenedor API (`db.init_db` + flujo auto-reply con lock/idempotencia/hilo) PASS.
      - `python3 tests/verify_hardening.py --check-api` PASS (usuario admin temporal de prueba).
      - `python3 tests/e2e_ticketera.py` PASS end-to-end.
    - Observación operativa:
      - Si el contenedor API no se reinicia tras deploy, `tickets.email_references` puede faltar hasta ejecutar migración (`db.init_db`).
  - Ajuste adicional de estabilidad E2E:
    - `JiraIssueIn` amplía contrato con `updated_at/updated` para conservar idempotencia real en `delta-sync` por payload.
- **Estado**: CERRADO (implementación y validación completa en DEV).

## HITO: 2026-02-15 06:10 - EPIC 11 fase técnica paralelo Jira+MONSTRUO + Go/No-Go
- **Solicitud**: Implementar siguiente fase EPIC 11 para paralelo Jira+MONSTRUO (8 semanas), con sincronización controlada, KPI diario y registro formal Go/No-Go.
- **Entregable**:
  - APIs nuevas protegidas por `tickets:compliance`:
    - `POST /api/tks/migration/jira/bootstrap-open`
    - `POST /api/tks/migration/jira/delta-sync/run`
    - `GET /api/tks/migration/jira/runs`
    - `GET /api/tks/migration/jira/reconciliation/daily`
    - `GET /api/tks/parallel/kpi/daily`
    - `POST /api/tks/parallel/go-no-go`
  - Persistencia Jira/paralelo:
    - tablas `jira_issue_map`, `jira_sync_runs`, `jira_sync_cursor`, `parallel_kpi_daily`, `parallel_decisions`.
    - índices de consulta para issue key, estado de run y snapshots diarios.
  - Motor de sincronización:
    - `bootstrap` y `delta` idempotentes por `jira_issue_key + jira_updated_at`.
    - cursor incremental para delta diario.
    - reconciliación y snapshot KPI diario con evidencia ISO.
  - Job recurrente:
    - `JIRA_DELTA_SYNC_DAILY` registrado en worker con reencolado anti-duplicado.
  - Gobernanza documental:
    - reconstruido `docs/PROGRAMA_REEMPLAZO_JIRA_ISO27001_12M.md` como fuente oficial activa.
    - creado `docs/playbooks/paralelo_jira_monstruo.md` para operación semanal y cierre.
  - Configuración:
    - variables `JIRA_*` añadidas a `config.py` y plantillas env (`.env.example`, `.env.local.example`, `docs/deploy/plantillas_env/*`).
- **Estado**: CERRADO PARCIAL (base técnica + gobernanza listas en DEV; pendiente ejecución operativa de 8 semanas en entorno productivo controlado).

## HITO: 2026-02-15 05:05 - Worker real de canales EPIC 11 (WhatsApp + 3CX prelisto)
- **Solicitud**: Implementar fase de escalamiento real por canales con activación controlada y separación DEV/PROD.
- **Entregable**:
  - State machine de notificaciones robusta en `ticket_notifications`:
    - estados operativos `pending`, `dispatching`, `sent`, `failed`, `cancelled`.
    - nuevos campos de entrega/reintento (`provider`, `provider_ref`, `last_error`, `attempt_count`, `max_attempts`, `next_retry_at`, `locked_at`, `updated_at`) + índices compuestos.
    - tabla nueva `ticket_notification_attempts` para trazabilidad por intento e idempotencia de retry manual.
  - Worker de integración real:
    - `code/app/workers/integrations_worker.py` reescrito con adapters HTTP agnósticos.
    - modos por canal `disabled|dry_run|live` + manejo de credenciales faltantes sin 500.
    - backoff exponencial acotado y corte por `max_attempts`.
  - API operativa mínima (RBAC `tickets:compliance`):
    - `GET /api/tks/channels/status`
    - `GET /api/tks/channels/notifications`
    - `POST /api/tks/channels/notifications/{notification_id}/retry` (idempotencia opcional por `Idempotency-Key`).
  - Configuración por entorno:
    - nuevas `CHANNELS_*`, `WHATSAPP_*`, `THREECX_*` en `config.py` y plantillas de entorno.
  - Tests:
    - `tests/e2e_ticketera.py` extendido con bloque de canales (dry_run, fallo controlado live sin credenciales, retry manual idempotente).
    - `tests/verify_hardening.py` extendido para rutas/variables de canales.
- **Estado**: CERRADO (fase técnica completada en DEV; activación live queda para siguiente fase con secretos por entorno).

## HITO: 2026-02-15 03:10 - Compliance Core EPIC 11 (inmutabilidad + export + retención/purga)
- **Solicitud**: Implementar cierre operativo de compliance en Ticketera para operación auditable (base ISO/IEC 27001).
- **Entregable**:
  - DB/migraciones:
    - `audit_logs` y `evidence_events` con hash-chain (`chain_prev_hash`, `chain_hash`, `chain_algo`, `chain_version`).
    - Backfill de cadena histórica y triggers append-only (`UPDATE/DELETE` bloqueados) para ambas bitácoras.
    - Nuevas tablas: `ticket_legal_holds`, `compliance_export_runs`, `compliance_purge_runs`.
    - `tickets.retention_days_snapshot` + backfill de `retention_until` para cerrados/resueltos.
  - Backend/API compliance:
    - Legal hold: `POST /api/tks/compliance/legal-holds`, `POST /api/tks/compliance/legal-holds/{hold_id}/release`, `GET /api/tks/compliance/legal-holds`.
    - Exportes: `POST /api/tks/compliance/exports/run` (idempotente), `GET /api/tks/compliance/exports/runs`.
    - Purga: `POST /api/tks/compliance/purge/dry-run`, `POST /api/tks/compliance/purge/run` (idempotente), `GET /api/tks/compliance/purge/runs`.
    - Integridad: `GET /api/tks/compliance/hash-chain/verify`.
  - Scheduling:
    - Jobs nuevos `COMPLIANCE_EXPORT_DAILY` (02:00) y `COMPLIANCE_PURGE_DAILY` (02:20) en `America/Santiago`.
  - Seguridad/RBAC:
    - Nuevo permiso `tickets:compliance` habilitado para rol `gerencia` (admin queda cubierto por wildcard).
  - Configuración/entorno:
    - Variables nuevas `COMPLIANCE_*` y `TICKET_RETENTION_*` en plantillas de entorno.
    - `.gitignore` actualizado para excluir `data/compliance/`.
- **Validación**:
  - `python3 tests/verify_hardening.py` PASS
  - `python3 tests/verify_hardening.py --check-api` PASS
  - `python3 tests/e2e_api_full.py` PASS
  - `python3 tests/e2e_ticketera.py` PASS (incluye bloque compliance: retención, legal hold, export idempotente, hash-chain verify, purge dry-run y purge run controlado)
- **Estado**: CERRADO (Compliance Core implementado en DEV; pendiente continuidad del programa Jira paralelo + evidencias ISO Stage 1/2).

## HITO: 2026-02-15 02:45 - Fix lentitud intermitente al cambiar a `/dev`
- **Solicitud**: Diagnosticar por qué a veces el entorno DEV cargaba lento o se quedaba pegado.
- **Causa observada**:
  - En proxy Nginx, el rewrite de prefijo estaba aplicando `sub_filter` también a CSS/JS, provocando buffering en disco (evidencia en `error.log`) y latencias variables.
  - El job de polling de correo corría trabajo IMAP en el loop async principal, pudiendo generar bloqueos puntuales del API.
- **Corrección aplicada**:
  - Proxy VM (`192.168.60.6`): `monstruo_prod_locations.conf` y `monstruo_dev_locations.conf` ajustados para reescritura de prefijo solo en HTML (sin filtro en CSS/JS) y recarga de Nginx validada (`nginx -t` + reload).
  - Backend: `poll_email_job` movido a ejecución en hilo (`asyncio.to_thread`) + timeout IMAP explícito en `EmailProcessor.connect`.
  - Frontend: botón de cambio de entorno del sidebar unificado a ruta canónica `__env` para evitar rutas ambiguas.
- **Validación**:
  - Pruebas en DEV:
    - `tests/verify_hardening.py --check-api` PASS
    - `tests/e2e_ticketera.py` PASS
  - Muestreo repetido de `https://login.telconsulting.cl/dev/` sin errores, con latencia estable (sin timeouts en la corrida final).
- **Estado**: CERRADO.

## HITO: 2026-02-15 02:20 - SLA horario hábil + escalamiento por ventana (EPIC 11)
- **Solicitud**: Avanzar con pendientes de Ticketera y verificar estabilidad completa de la app.
- **Entregable**:
  - Se incorpora configuración SLA por entorno:
    - `TICKET_SLA_MODE` (`24x7` | `business_hours`)
    - `TICKET_SLA_BUSINESS_TZ_OFFSET`
    - `TICKET_SLA_BUSINESS_DAYS`
    - `TICKET_SLA_BUSINESS_START_HOUR`
    - `TICKET_SLA_BUSINESS_END_HOUR`
    - `TICKET_SLA_ESCALATION_WINDOWS_PCT`
  - Motor SLA actualizado:
    - cálculo de `frt_due_at` y `ttr_due_at` compatible con calendario hábil;
    - alertas por ventanas de porcentaje configurables (dedupe por prefijo de evento);
    - métricas SLA enriquecidas con `sla_mode`, `business_hours` y `escalation_windows_pct`.
  - Hardening/E2E actualizados para contrato SLA extendido.
  - Verificación funcional ejecutada en DEV:
    - `tests/verify_hardening.py --check-api` PASS
    - `tests/e2e_api_full.py` PASS
    - `tests/e2e_ticketera.py` PASS
- **Estado**: CERRADO (SLA con calendario y escalamiento implementado; modo por defecto sigue en 24x7 para compatibilidad hasta activación operacional por entorno).

## HITO: 2026-02-15 01:10 - Cierre Bloque Workflow + SLA (EPIC 11) en DEV
- **Solicitud**: Implementar cierre técnico-operativo del bloque pendiente `Workflow + SLA` de EPIC 11 sin romper compatibilidad.
- **Entregable**:
  - Backend Ticketera ampliado con workflow formal por tipo (`incidencia`, `requerimiento`, `cambio`) usando `estado` + `subestado`.
  - Nuevos endpoints:
    - `GET /api/tks/tickets/{ticket_id}/workflow`
    - `POST /api/tks/tickets/{ticket_id}/transitions`
    - `POST /api/tks/tickets/{ticket_id}/approvals`
    - `GET /api/tks/tickets/{ticket_id}/approvals`
  - Doble aprobación para `cambio` operativa (paso 1 + paso 2) con bloqueo de ejecución sin ambas aprobaciones.
  - SLA 24x7 formalizado con `first_response_at`, `frt_due_at`, `ttr_due_at`, `resolved_at`, `frt_breached_at`, `ttr_breached_at`, `aging_minutes_open` y endpoints SLA extendidos.
  - Idempotencia reforzada en transiciones/aprobaciones (dedupe real en reintentos con `Idempotency-Key`).
  - Frontend Ticketera actualizado con selector de tipo, panel de workflow/aprobaciones e indicadores SLA.
  - Migraciones y backfill aplicados para nuevas columnas/tablas (`ticket_transitions`, `ticket_approvals` + índices).
  - Pruebas actualizadas y en verde:
    - `tests/e2e_ticketera.py` PASS
    - `tests/e2e_api_full.py` PASS
    - `tests/verify_hardening.py --check-api` PASS
- **Estado**: CERRADO (fase Workflow + SLA base 24x7 completada en DEV; pendiente fase de horario hábil/calendario y escalamiento por ventana).

## HITO: 2026-02-14 23:50 - Activacion Programa Reemplazo Jira + ISO/IEC 27001 (12 meses)
- **Solicitud**: Implementar plan maestro de reemplazo Jira y certificacion ISO/IEC 27001 con foco operativo en EPIC 11.
- **Entregable**:
  - Documento canonico creado: `docs/PROGRAMA_REEMPLAZO_JIRA_ISO27001_12M.md` con cronograma, criterios de salida, controles y entregables de auditoria.
  - `PLAN_MAESTRO_MONSTRUO.md` actualizado con:
    - nueva seccion `0.8` (programa activo),
    - backlog EPIC 11 alineado a reemplazo Jira + SGSI.
  - Backend Ticketera extendido para soporte del plan:
    - APIs nuevas: adjuntos por ticket, emails `format=human`, SLA metrics/breaches, automations rules, migration Jira import, evidencia ISO.
    - Tipo `ticket_security_class` y tabla `evidence_events`.
    - Convencion `Idempotency-Key` aplicada a reply-email.
    - Hardening: eventos de evidencia quedan `best-effort` para evitar 500 post-accion real.
- **Estado**: EN CURSO (programa activado y baseline tecnico implementado en DEV; pendientes cierre operativo y auditoria externa).

## HITO: 2026-02-14 23:00 - Cierre Definitivo Gobernanza (EPIC 11)
- **Acción**: Eliminación total de secretos hardcodeados en scripts de seed (`setup_users.py`).
- **Validación**: Barrido de seguridad (grep) limpio y re-ejecución exitosa de suite E2E.
- **Estado**: GOBERNANZA CUMPLIDA. Repositorio en regla.

## HITO: 2026-02-14 22:00 - Cierre Técnico E2E Ticketera (DEV)
- **Solicitud**: Completar E2E con prueba de `incoming thread match` y hardening de deploy.
- **Entregable**:
  - `e2e_ticketera.py` ahora valida ciclo completo: creates -> reply (outgoing) -> incoming match (simulado).
  - `verify_hardening.py` valida configuración de deploy en `dev`.
  - Reporte de ejecución exitosa en `docs/playbooks/e2e_ticketera_dev_validacion.md`.
  - `PLAN_MAESTRO_MONSTRUO.md` actualizado con evidencia real.
- **Estado**: COMPLETADO (Técnico). Pendiente certificación administrativa (Go/No-Go).

## HITO: 2026-02-14 21:00 - Validación E2E Ticketera en DEV
- **Solicitud**: Ejecutar y cerrar validación E2E de Ticketera en DEV con evidencia completa.
- **Entregable**:
  - Suite obligatoria ejecutada en DEV (`verify_hardening`, `check-api`, `e2e_api_full`, `e2e_ticketera`) con resultado **PASS**.
  - Evidencia de flujo completo: Login, Creación Ticket, Respuesta, Hilos de correo, Anti-duplicado.
  - Validación de seguridad: Sin credenciales hardcodeadas, separación DEV/PROD confirmada.
  - Documentación actualizada: EPIC 11 en Plan Maestro marcado como completado en items de testing y hardening.
- **Estado**: CERRADO.

## HITO: 2026-02-14 19:40 - Hardening documental anti-cruce DEV/PROD
- **Solicitud**: Actualizar Prompt Universal y reforzar reglas para evitar mezcla entre DEV y PROD.
- **Entregable**:
  - `docs/PROMPT_CHAT_UNIVERSAL.md` reescrito como bootstrap vigente (orden de autoridad, carga obligatoria de `ESTANDARES.md`, uso obligatorio de allowlists `.README.md`, matriz DEV/PROD y checklist anti-cruce).
  - `docs/ESTANDARES.md` corregido con ruta real del generador de prompt:
    - `ops/herramientas/deploy/generate_universal_prompt.py`
  - `docs/deploy/README.md` corregido para usar nombres reales de plantillas Nginx (`.md`).
  - `docs/.README.md` actualizado para reflejar allowlist vigente (`deploy/`, `ia/`, `sql/`, `windows/`) y nombre correcto `PLAN_MAESTRO_MONSTRUO.md`.
  - Permisos de documentación normalizados (sin bit ejecutable en `.md`).
- **Estado**: CERRADO.

## HITO: 2026-02-14 17:10 - Desambiguación de nombres (PMO/routers/wrappers legacy)
- **Solicitud**: Evitar archivos con el mismo nombre cuando representan funciones distintas.
- **Entregable**:
  - PMO renombrado para claridad:
    - `code/static/modulos/pmo/dashboard.html` -> `code/static/modulos/pmo/pmo.html`
    - referencias actualizadas en `main.py` y `sidebar.js`.
  - Routers API renombrados para evitar ambigüedad con capa core:
    - `audit.py` -> `audit_router.py`
    - `bridge.py` -> `bridge_router.py`
    - `config.py` -> `config_router.py`
  - Wrappers legacy renombrados explícitamente:
    - `code/app/workflow_db.py` -> `code/app/workflow_db_legacy.py`
    - `code/app/utils/ai_init.py` -> `code/app/utils/ai_init_legacy.py`
    - `code/app/utils/ai_local_openai_compat.py` -> `code/app/utils/ai_local_openai_compat_legacy.py`
  - Smoke validado:
    - `docker compose config` DEV y PROD OK.
    - Healthcheck `:9001` y `:9000` OK.
    - Ruta nueva PMO (`/modulos/pmo/pmo.html`) OK.
    - Ruta antigua PMO (`/modulos/pmo/dashboard.html`) responde 404 esperado.
- **Estado**: CERRADO.

## HITO: 2026-02-14 16:20 - Limpieza de raiz: plantillas .env centralizadas
- **Solicitud**: Reducir ruido por exceso de archivos `.env*` en la raiz del repositorio.
- **Entregable**:
  - Plantillas movidas desde raiz a `docs/deploy/plantillas_env/`:
    - `env.base.example`
    - `env.local.example`
    - `env.server.example`
    - `env.server.dev.example`
  - Documentación de deploy actualizada para usar rutas nuevas de plantillas.
  - `.gitignore` simplificado (sin excepciones de `.env.*` versionados en raiz).
  - Raiz queda enfocada en archivos operativos reales (`.env`, `.env.server`, `.env.server.dev`) y no plantillas.
- **Estado**: CERRADO.

## HITO: 2026-02-14 20:20 - Hardening OPS subido a `dev` + Profesionalización carpeta `tests/`
- **Solicitud**: Subir hardening operativo a GitHub (`dev`) y dejar `tests/` en estándar profesional con registro oficial.
- **Entregable**:
  - Push confirmado a `origin/dev` del hardening OPS (`commit: 2a04e5b`).
  - `tests/` estandarizado:
    - Nuevo helper común: `tests/_helpers.py`.
    - Scripts sin credenciales hardcodeadas y parametrizados por ENV/CLI:
      - `tests/e2e_api_full.py`
      - `tests/e2e_ticketera.py`
      - `tests/verify_hardening.py`
    - Guardas anti-PROD por defecto (`--allow-prod` explícito para bypass controlado).
    - Nuevo manifiesto local: `tests/.README.md` (allowlist + política operativa).
  - Gobernanza de estructura actualizada:
    - `docs/estructura_repo.json` ahora incluye raíz `tests` y regla de extensiones.
    - Árbol oficial detallado en `docs/PLAN_MAESTRO_MONSTRUO.md` actualizado para `tests/`.
- **Estado**: CERRADO.

## HITO: 2026-02-14 19:05 - Gobernanza de Agentes DEV + Prioridad EPIC 11
- **Solicitud**: Subir Plan Maestro actualizado y formalizar reglas de agentes para entorno DEV, dejando obligatorio el uso de `monstruo-dev-reglas.md`.
- **Entregable**:
  - Agregado `AGENTS.md` en la raiz para obligar bootstrap de reglas en agentes compatibles.
  - Creado archivo canonico: `.agent/rules/monstruo-dev-reglas.md`.
  - Regla legacy eliminada para evitar ambiguedad; queda un unico archivo canonico de reglas en DEV.
  - Plan Maestro actualizado con seccion de gobernanza obligatoria para agentes (`0.7`) y prioridad de EPIC 11 para reemplazo de mesa externa.
  - Criterio explicito: no se abre desarrollo neto de EPIC 12+ hasta cerrar EPIC 11 con Go/No-Go profesional.
- **Estado**: CERRADO.

## HITO: 2026-02-14 18:05 - Fix CI/CD Deploy DEV (tests OK, deploy fail)
- **Incidente**: GitHub Actions mostraba `tests` OK pero `deploy` fallaba en rama `dev`.
- **Causa raiz**: Drift entre `project` de Docker Compose (`monstruo-dev` vs `monstruo_dev`) con `container_name` fijo; Compose detectaba conflicto de ownership y abortaba con "container name already in use".
- **Corrección aplicada**:
  - Workflow actualizado en `.github/workflows/deploy.yml`:
    - `dev` ahora usa `project=monstruo_dev` (estable).
    - `dev` mantiene `stack=monstruo-dev` (nombre legible de contenedores).
  - Método operativo documentado en `docs/deploy/README.md` (separación correcta `project` vs `stack` y regla de estabilidad).
- **Método correcto (estándar)**:
  - `main`: `project=monstruo`, `stack=monstruo`.
  - `dev`: `project=monstruo_dev`, `stack=monstruo-dev`.
  - Nunca alternar guion/guion_bajo en `project` una vez creado el ambiente.
- **Estado**: CERRADO.

## HITO: 2026-02-14 15:40 - Ticketera Correo en Hilo + Reset DEV
- **Solicitud**: Responder correos desde el detalle del ticket, mantener cadena de correo y dejar ticketera en cero para partir limpio en dev.
- **Entregable**:
  - Endpoint nuevo `POST /api/tks/tickets/{ticket_id}/reply-email`.
  - UI de respuesta por correo en detalle de ticket (textarea + envío).
  - Envío con headers de hilo (`In-Reply-To`, `References`) y actualización de `email_thread_id`.
  - Protección anti-duplicado de envíos por reintento (dedupe por ventana corta + marcador `outgoing_pending`).
  - Parser de correo entrante mejorado: match por hilo y por código en asunto.
  - Formato de código de ticket actualizado a `TK-DD-MM-YYYY-NNNN` (compatibilidad con formato anterior).
  - Limpieza total de ticketera en entorno dev (`tickets`, `ticket_comments`, `ticket_notifications`, `ticket_emails`, `ticket_attachments`) + reset de `current_load`.
- **Estado**: CERRADO.

## HITO: 2026-02-08 08:35 - Configuración Flujo Git/GitHub Automático
- **Solicitud**: Configurar despliegue automático desde GitHub (Push-to-Deploy) compatible con firewall estricto.
- **Entregable**: 
  - Repositorio remoto vinculado: `git@github.com:JCtelconsulting/MONSTRUO.git`.
  - Autorización SSH (Deploy Key "SERVIDOR").
  - Workflow `deploy_monstruo.yml` para Self-Hosted Runner.
  - Documentación `README.md` creada.
  - **Fix Runner:** Reconfigurado servicio systemd para ejecutar como usuario `juan` y movido a `/srv/monstruo_dev/runner` (Solución a Permission Denied).
- **Estado**: CERRADO.

## HITO: 2026-02-07 19:59 - Diagnóstico y Corrección de Permisos Git/Sistema
- **Solicitud**: Recuperar control de carpeta `/srv/monstruo` (pertenecía a deploy) e inicializar versionamiento.
- **Entregable**: 
  - Propiedad de carpeta transferida al usuario actual.
  - Repositorio git inicializado (`main`) y marcado como `safe.directory`.
  - Estructura de documentación validada.
- **Estado**: CERRADO.

## HITO: 2026-02-05 20:15 - Estabilización y Fixes de Fondo
- **Smart Match:** Implementado motor de conciliación automática con heurística de monto + referencia de glosa (Factura ID).
- **Optimización WSL:** Reducción de tope de RAM a 3GB y botones de control en escritorio.
- **Sistema Healthy:** Corregidos servicios systemd (Guardian) y bug en motor de jobs (Type mismatch in Billing Job).
- **Estado: CERRADO (Healthy)**

## Proposito (contexto de conversaciones IA)
Este documento guarda el hilo de las conversaciones con IA en forma de hitos ordenados. Aqui se ve el camino (antes/despues). El Plan Maestro solo refleja el estado final.

## Rango cubierto
- Semana activa: 2026-01-20 a 2026-02-01 (consolidado de conversaciones).

## Estado actual (resumen corto)
- Gate A casi cerrado: backend listo; falta UI que oculta menus segun permisos (EPIC 02).
- Gate B completado: conciliacion bancaria end-to-end (EPIC 07) - **Esperando cartolas CSV reales**.
- Gate C pendiente: IA Bodega asistida (EPIC 10).
- EPIC 01 Frontend completado: ERP y Bodega modularizados por pestaña.
- Bodega UI refinada: categorías homogéneas en inventario y asignación masiva en catálogo.
- Pendientes mayores: Jira sync (EPIC 12), Zabbix->Ticket (EPIC 13), JP (EPIC 14), Preventa (EPIC 15), Reporting (EPIC 16), ULTRON (EPIC 17).

## Hitos por modulo (cronologico y sin duplicados)

### Plataforma base / Infra / Repo
- 2026-01-20: Genesis del proyecto. Setup FastAPI + SQLite.
- 2026-01-24: Hardening inicial (systemd y backups).
- 2026-01-27: Reorganizacion total del repo (EPIC 01). Arbol canonico, manifiestos estrictos y estructura modular.
- 2026-01-27: Migracion `code/backend` -> `code/app` y `code/scripts` -> `code/procesos`.
- 2026-01-27: Reorg frontend a `code/static/modulos/` (component-based).
- 2026-01-29: PostgreSQL local con Docker + migracion SQLite->Postgres completada.
- 2026-02-01: EPIC 01 Frontend completado - ERP y Bodega modularizados por pestaña.
- 2026-02-04: **Migracion Completa a Docker Monstruo** - Eliminacion de infraestructura legacy (systemd). Creacion de `Dockerfile.api`, correccion de rutas estaticas, resolucion de conflictos de puertos (9000 API, 8000 ws-scrcpy). Sistema 100% containerizado.
- 2026-02-04: **Modulo Bancos Operativo** - Streaming Android (V30 Lite) funcionando en vivo dentro del ERP. Fix de permisos ADB en WSL2, configuracion ws-scrcpy en puerto 8000, correccion de dimensiones iframe (zoom 240% -> 100%). Dispositivo `10AE1G1FAY0014H` detectado y transmitiendo apps bancarias (MACH visible, Banco Estado con error esperado del proveedor).

### Frontend / UX
- 2026-01-22: Dashboard inicial (Aging, Top Deudores) + login.
- 2026-01-25: UI modular propia (sin portal legacy). Sidebar y navegacion unificada.
- 2026-01-26: Bodega UX: search-as-you-type + fixes visuales en arbol categorias.
- 2026-01-29: Bodega UI: busqueda case-insensitive, Kardex en drawer, normalizacion visual.

### Auth / RBAC / Auditoria
- 2026-01-28: JWT + refresh + RBAC por router (EPIC 02 backend completado).
- 2026-01-28: Auditoria global con decorador y export (EPIC 03 completado).
- Estado actual: falta UI para ocultar menus segun permiso.

### Jobs / Integraciones (motor)
- 2026-01-28: Motor de jobs persistente con retry + DLQ (EPIC 04 completado).
- 2026-01-29: Dashboard Ops alineado a esquema real.

### ERP (Ventas)
- 2026-01-28: Facturacion completa (Draft->Issued->Paid/Void) con NC/ND y stock integrado (EPIC 05 completado).
- 2026-01-28: Proxy Laudus PDF + pagos (espejo).

### CRM (Clientes)
- 2026-01-28: Sync clientes Laudus + API local (EPIC 06 completado).

### ERP (Conciliacion Bancaria)
- 2026-02-01: Conciliacion bancaria completa (EPIC 07 completado).
  - Infraestructura DB (4 tablas): bank_accounts, statements, lines, reconciliations.
  - Parser CSV multi-banco (Santander, BCI).
  - Motor de matching (exacto 100% + fuzzy 80%).
  - Sync automatico con Laudus ledger.
  - UI profesional alineada a modulo Facturacion.
  - **LIMITACION:** Esperando cartolas CSV reales del banco para uso en produccion.
  - **FALLBACK:** Sistema probado con CSV sintetico (4 matches detectados exitosamente).

### Bodega / Catalogo
- 2026-01-25: Catalogo maestro v2, pendientes y dedupe IA local (flujo inicial).
- 2026-01-26: Duplicados y busqueda case-insensitive en inventario.
- 2026-01-28: Catalogo maestro + Kardex + movimientos (EPIC 09 completado).
- 2026-01-29: Multi-categoria + filtro con subcategorias + categorias madre EQUIPOS/MATERIALES.
- 2026-01-30: Soporte de Imágenes en Catálogo (Backend/Frontend).
- 2026-01-30: Bodega UI: Modal de Resolución de Duplicados con soporte visual y manejo de Variantes.
- 2026-01-30: Selector de Categorías Jerárquico con creación inline.
- 2026-01-31: Definición de Estándar UI: Módulo ERP es el referente visual obligatorio (Tabs, KPIs, Tablas).
- 2026-02-01: Bodega UI: categorías en inventario con rutas homogéneas (niveles 2-4), catálogo con selección múltiple y asignación masiva, búsqueda y conteos en árbol.
- Estado actual: IA asistida en proceso de refinamiento (Feedbck loop activo).

### Ticketera
- 2026-01-28: Ticketera v1 completa + SLA + adjuntos + timeline (EPIC 11 completado).
- 2026-01-29: Discrepancias crean tickets en vez de auto-ajustes (EPIC 100 completado).

### IA / ULTRON
- 2026-01-25: Renombre Jarvis -> ULTRON. Endpoints IA base + politicas.
- 2026-01-25: Integracion IA local (Ollama) y soporte dataset bodega.

### Integraciones externas (Laudus / Parrotfy)
- 2026-01-21: Laudus POC (clientes + facturas).
- 2026-01-24: Parrotfy discovery (swagger) + staging; facturas OK.
- 2026-01-24 a 2026-01-29: Parrotfy pagos falla con error 500 (pendiente ticket proveedor).
- 2026-01-28: Laudus proxy PDF + pagos espejo.

### Guardian (ops)
- 2026-01-27: Guardian creado (estructura, BD SQLite, vigilantes, supervisor, envio, timers).
- Estado actual: servicios y timers definidos; mantener verificacion periodica.

## Progresiones importantes (antes -> despues)
- Auth: session simple -> JWT + RBAC + auditoria (falta UI permisos).
- Bodega: categorias duplicadas -> Taxonomía Estricta (Backend OK), UI Pendiente revisión.
- Discrepancias: auto-ajuste -> crea tickets de alta prioridad.
- Stock: fuente incierta -> Laudus como source of truth + sync controlado.

## Referencias rapidas
- Parrotfy OpenAPI local: `docs/apis/parrotfy_openapi.yaml`
- Parrotfy Spec URL: `https://telconsulting.parrotfy.com/api-docs/v1/swagger-es.yaml`
- Endpoints clave: `/api/v1/inventory_movements/stock`, `/api/v1/products`

## Proximos pasos (orden sugerido)
1) Cerrar Gate A: UI que oculta menus segun permisos.
2) EPIC 10: IA Bodega asistida (sugerencias + revision humana).
3) EPIC 12: Jefe Proyectos PMO (Fase 1 completada - Refinar IA).
4) EPIC 13: Jira sync minimo viable.
5) EPIC 14: Zabbix -> Ticket (webhook, dedupe, incidentes).
6) EPIC 15-18: Preventa, Reporting, ULTRON, Housekeeping.

HITO: 2026-02-05 14:50 - Integración CRM + Facturación Automática
- Implementado selector de clientes CRM en modal de reglas de facturación.
- Corregido estilo visual del modal (tema neón y centrado).
- Resuelto bug 404 por conflicto de puertos con contenedor Docker fantasma.
- ESTADO: CERRADO

## Registro de conversaciones (formato corto)
### 2026-02-05 10:20 - Foco en Finanzas y Cierre de Bancos
- Solicitud: El usuario pide cerrar el tema de Bancos y girar el foco hacia Finanzas, Facturación y Cobranza.
- Entregable:
  - **Plan Maestro:** EPIC 20 (Bancos) marcado como COMPLETADO. EPICs 21, 22 y 23 reformateados y detallados para el enfoque de Finanzas.
  - **Bancos:** Módulo 100% operativo con control de sesión exclusivo y streaming vía ws-scrcpy.
- Estado: **EN CURSO** (Iniciando tareas de Finanzas).

### 2026-02-05 08:45 - Cambio de Red y IP Móvil (Bancos)
- Solicitud: El usuario cambió de WiFi; la nueva IP del teléfono es `192.168.20.230:39425` (pairing) y `42419` (connection).
- Entregable: 
  - **Docker:** Actualizado Dockerfile de `ws-scrcpy` a platform-tools v36.
  - **ADB:** Sincronización de llaves RSA y vinculación (pair) exitosa.
  - **UI:** Iframe actualizado en `bancos.html`.
- Estado: **CERRADO**. Conexión estable en estado `device`.

### 2026-02-04 16:50 - Levantamiento de App y Extensión ERP (RRHH)
- Solicitud: levantar la aplicación y terminar el área de ERP para Recursos Humanos (Buk).
- Entregable: Sistema operativo y nueva pestaña de RRHH en el módulo ERP con integración base de Buk.
- Estado: EN CURSO.

### 2026-02-01 22:10 - Bodega UX y Catálogo (cierre sesión)
### 2026-02-02 09:15 - Inicio de sesión y arranque de app
- Solicitud: revisa el plan maestro y el proyecto contexto y hecha a andar la app porfavor
- Entregable: App corriendo (Postgres via Docker + Uvicorn manual en puerto 9000). Systemd falló por falta de credenciales SUDO no interactivo.
- Estado: CERRADO.

### 2026-02-01 22:10 - Bodega UX y Catálogo (cierre sesión)
- Solicitud: homogeneizar categorías en inventario, mover items en lote y limpiar UI de catálogo.
- Entregable:
  - Inventario: rutas de categorías homogéneas y sin duplicar rutas padre/hija.
  - Catálogo: selección múltiple + asignación masiva; barra de búsqueda; botón IA removido; conteos en árbol y lógica de “Sin Asignar” corregida.
  - Stock negativo revisado: origen Laudus (SYNC), sin movimientos locales extraños.
  - Archivos tocados: `code/static/modulos/bodega/bodega.html`, `code/static/modulos/bodega/js/bodega_ui.js`, `code/static/modulos/bodega/js/bodega_core.js`, `code/static/modulos/bodega/catalogo/catalogo.html`, `code/static/modulos/bodega/inventario/inventario.html`, `code/app/core/bodega_service.py`.
- Estado: cerrado.

### 2026-02-01 11:30 - Limpieza Profunda y Auditoría Estructural (EPIC 18)
- Solicitud: Eliminar soporte legacy (SQLite), limpiar raíz y validar estructura estricta.
- Entregable:
    - **Código:** `db.py` forzado a PostgreSQL. Eliminados logs y temporales.
    - **Backups:** Movidos todos a `/srv/monstruo_old/` (política de backup externo).
    - **Auditoría:** `verify_structure.py` reporta **0 Violaciones**.
    - **Docs:** Manifiestos `.README.md` actualizados y Plan Maestro sincronizado.
- Estado: CERRADO.

### 2026-01-30 10:22 - Autoarranque servidor en Windows (WSL)
- Solicitud: que el servidor se prenda al iniciar Windows.
- Entregable: servicio habilitado en systemd (si habia permisos) y tarea programada en Windows (ONLOGON).
  - Archivos tocados: docs/PROYECTO_CONTEXTO.md (modificado).

- Estado: cerrado
- Paso ejecutado:

### 2026-01-30 11:30 - Bodega IA: Imágenes, Variantes y Categorización
- Solicitud: Mejorar identificación visual y manejo de "falsos duplicados" (variantes).
- Entregable:
  - **Imágenes:** Columna `image_url` en DB + visualización en tablas y modales.
  - **Variantes:** Flujo para marcar items como variantes y asignarles categoría común.
  - **Wizard Categorías:** Selector jerárquico JS con creación de categorías al vuelo.
  - **Logs:** Registro de feedback humano para entrenamiento futuro de la IA.
  - Archivos tocados: `db.py`, `catalogo.py`, `ai.py`, `bodega.html`, `bodega_ui.js`, `bodega_core.js`, `category_tree.js` (nuevo).
- Estado: cerrado (funcionalidad base implementada).
  - Objetivo: crear tarea programada Windows (schtasks) para WSL.
  - Resumen: distro=Ubuntu, usuario=juan, task=Monstruo-Autoinicio, task_ok=0.
  - Verificacion: schtasks /Query /TN Monstruo-Autoinicio.
  - Rollback: schtasks /Delete /TN Monstruo-Autoinicio /F.
- Paso ejecutado (2026-01-30 10:27):
  - Objetivo: crear tarea programada Windows (schtasks) sin -e.
  - Resumen: distro=Ubuntu, usuario=juan, task=Monstruo-Autoinicio, task_ok=0.
  - Verificacion: schtasks /Query /TN Monstruo-Autoinicio.
  - Rollback: schtasks /Delete /TN Monstruo-Autoinicio /F.
- Paso ejecutado (2026-01-30 10:30):
  - Objetivo: crear tarea programada Windows (schtasks) con systemctl directo.
  - Resumen: distro=Ubuntu, usuario=juan, task=Monstruo-Autoinicio, task_ok=0, sudo_ok=1.
  - Verificacion: schtasks /Query /TN Monstruo-Autoinicio.
  - Rollback: schtasks /Delete /TN Monstruo-Autoinicio /F.
- Paso ejecutado (2026-01-30 10:31):
  - Objetivo: crear tarea programada Windows (schtasks) con wsl.exe quoted.
  - Resumen: distro=Ubuntu, usuario=juan, task=Monstruo-Autoinicio, task_ok=0.
  - Verificacion: schtasks /Query /TN Monstruo-Autoinicio.
  - Rollback: schtasks /Delete /TN Monstruo-Autoinicio /F.
- Paso ejecutado (2026-01-30 10:34):
  - Objetivo: crear bat en Windows y tarea programada ONLOGON.
  - Resumen: bat=/mnt/c/Users/juane/monstruo/iniciar_monstruo.bat, distro=Ubuntu, usuario=juan, task=Monstruo-Autoinicio, task_ok=0, sudo_ok=1.
  - Verificacion: schtasks /Query /TN Monstruo-Autoinicio.
  - Rollback: schtasks /Delete /TN Monstruo-Autoinicio /F y borrar iniciar_monstruo.bat.
- Paso ejecutado (2026-01-30 10:36):
  - Objetivo: crear autoarranque Windows (schtasks o Startup).
  - Resumen: bat=/mnt/c/Users/juane/monstruo/iniciar_monstruo.bat, distro=Ubuntu, usuario=juan, task=Monstruo-Autoinicio, task_ok=0, startup_ok=1.
  - Verificacion: schtasks /Query /TN Monstruo-Autoinicio o revisar Startup. 
  - Rollback: schtasks /Delete /TN Monstruo-Autoinicio /F y borrar /mnt/c/Users/juane/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/iniciar_monstruo.bat.
- Paso ejecutado (2026-01-30 10:43):
  - Objetivo: crear tarea programada con privilegios (RunAs).
  - Resumen: user_win=juane, task=Monstruo-Autoinicio, bat=C:\Users\juane\monstruo\iniciar_monstruo.bat, query_ok=0.
  - Verificacion: schtasks /Query /TN Monstruo-Autoinicio.
  - Rollback: schtasks /Delete /TN Monstruo-Autoinicio /F.
- Paso ejecutado (2026-01-30 10:58):
  - Objetivo: diagnosticar autoarranque (tarea + bat + servicio).
  - Resumen: se consulto tarea y se ejecuto bat manualmente (C:\Users\juane\monstruo\iniciar_monstruo.bat).
  - Verificacion: systemctl is-active/status en WSL.
  - Rollback: no aplica.
- Paso ejecutado (2026-01-30 10:59):
  - Objetivo: corregir bat para ejecutar como root y reintentar start.
  - Resumen: bat actualizado (C:\Users\juane\monstruo\iniciar_monstruo.bat).
  - Verificacion: systemctl is-active/status.
  - Rollback: restaurar bat anterior si fuese necesario.
- Paso ejecutado (2026-01-30 11:00):
  - Objetivo: incluir inicio de Postgres (docker compose) antes del API.
  - Resumen: bat actualizado (C:\Users\juane\monstruo\iniciar_monstruo.bat) para docker compose + systemctl.
  - Verificacion: docker compose ps y systemctl is-active.
  - Rollback: restaurar bat anterior si fuese necesario.
### 2026-01-30 09:08 - Reordenamiento PROYECTO_CONTEXTO
- Solicitud: ordenar contexto con historico en hitos y evitar repetidos.
- Entregable: PROYECTO_CONTEXTO reestructurado en hitos por modulo y resumen semanal.
- Estado: cerrado
- Paso ejecutado:
  - Objetivo: mover historico a backups y registrar hito.
  - Archivos tocados: docs/PROYECTO_CONTEXTO.md (modificado), docs/PROYECTO_CONTEXTO_HISTORICO_2026-01-30.md (movido), backups/2026-01-30/090748__docs_PROYECTO_CONTEXTO.md (creado).
  - Resumen: historico movido a backups con formato canonico y registro agregado.
  - Verificacion: verificacion en bloque de comandos (ls/rg/test).
  - Rollback: restaurar archivo desde backups/2026-01-30/.


### 2026-01-31 22:00 - Refinamiento PMO Dashboard & Auditoría (Cierre)
- Solicitud: Refinar UI Dashboard (Layout 3 columnas), implementar edición inline (acordeón), gestión de estados y auditoría.
- Entregable: 
    - Dashboard PMO V3 con "Wide Cards" y Acordeón.
    - Ciclo de vida completo (Borrador -> Cerrado) con feedback visual.
    - Backend robusto: Endpoint PATCH async con inyección de dependencias para Auditoría.
    - Corrección de infraestructura: Migración columna 'estado' en PostgreSQL y limpieza de procesos zombies.
- Estado: CERRADO.

### 2026-01-31 22:30 - Reorganización y Limpieza Plan Maestro
- Solicitud: Ordenar EPICs secuencialmente (10-18), eliminar duplicados y mejorar formato visual.
- Entregable:
    - **Renumeración:** PMO (EPIC 12), Jira (EPIC 13), Zabbix (EPIC 14), Preventa (EPIC 15)... Housekeeping (EPIC 18).
    - **Formato:** Separadores visuales (`---`) entre Capítulos, Gates y EPICs.
    - **Reglas:** Política de "Secuencialidad y Unicidad" movida al inicio del listado.
- Estado: CERRADO.

### 2026-02-01 13:00 - EPIC 07 Bank Reconciliation (Completo)
- Solicitud: Habilitar conciliación bancaria en ERP (UI + Carga de Cartolas + Motor de Matching).
- Entregable:
    - **Backend:** Tablas `bank_accounts`, `bank_statements`, `bank_statement_lines`, `bank_reconciliations`.
    - **API:** Router `/api/conciliacion` con 7 endpoints (banks, upload, sync, movements, statements, match, matches).
    - **Parser:** Soporte multi-banco (Santander, BCI) con validación de formato.
    - **Matcher:** Motor de matching con estrategias Exacta (100%) y Fuzzy (80%).
    - **Sync:** Script `sync_bancos_laudus.py` + endpoint `/sync` para obtener ledger automáticamente.
    - **UI:** Tab "Conciliación" rediseñado con estilo profesional igual a "Facturación".
    - **Testing:** CSV sintético generado y probado (4 matches exactos detectados).
    - **Bugs Corregidos:** PostgreSQL placeholders, missing SQL execution, API prefix, amount parsing.
- Hallazgos:
    - Laudus API no expone `/accounting/journal-entries` (404).
    - Conciliación interna (manual vs imported) requiere heurísticas; postponed.
- **LIMITACIÓN:** Sistema funcional pero requiere cartolas CSV reales del banco para producción.
- Estado: CERRADO - Esperando CSVs bancarios.

### 2026-02-01 17:30 - EPIC 08 Cobranza: Gestión y Automatización Email (Fase 1-3)
- Solicitud: Automatizar la gestión de cobranza y envío de correos, con configuración flexible.
- Entregable:
    - **Dashboard Deuda:** Listado con semáforo de riesgo (30/60/90 días) y filtros.
    - **Gestión:** Modal para registrar llamadas/correos, persistente en tabla `collection_actions`.
    - **Infraestructura Email:** Servicio `app.core.email.py` (SMTP) + Tabla `system_settings` para credenciales.
    - **Config UI:** Tarjeta de configuración SMTP en pestaña Resumen (sin reiniciar servidor).
    - **Wiring:** Botón "Generar Borrador" crea asunto/cuerpo inteligente y "Guardar" envía el correo real si es tipo EMAIL.
    - **Fixes Visuales:** Origen Factura (Laudus/Local) corregido, Nombres de Clientes normalizados (Title Case).
- Estado: FUNCIONAL (Credenciales SMTP requeridas para envío real).

### 2026-02-01 20:50 - Debugging Infraestructura y UX (Cierre Sesión)
- **Incidente Crítico:** Puerto 9000 bloqueado por proceso zombie `root`.
  - Solución: Eliminación manual de PID y reinicio de servicio `monstruo-api`.
- **KPIs Resumen:**
  - Problema: Mostraban 0 (por lógica de mes calendario v/s día 1 del mes) o Error 500.
  - Solución: Lógica ajustada a "Rolling 30 days", fix de nulos en DB y recarga automática al cambiar de pestaña.
- **Estado Final:** Sistema estable, visualizando datos reales y listo para operar.
