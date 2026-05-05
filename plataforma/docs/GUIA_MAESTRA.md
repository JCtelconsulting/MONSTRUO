# Guía Maestra Monstruo

> **Versión**: v2 (2026-05-05). Reescrita desde cero, sin la deuda histórica de la v1.
> La v1 (2289 líneas con bitácoras + árbol de carpetas + EPICs futuros) quedó archivada en [archive/GUIA_MAESTRA_v1_2026-02.md](archive/GUIA_MAESTRA_v1_2026-02.md) por contexto histórico.
> EPICs no implementados se conservan en [archive/EPICS_FUTUROS.md](archive/EPICS_FUTUROS.md) por si se reactivan.
> La estructura de carpetas del repo NO se documenta acá: cambia a menudo y se mantiene sola por la convención (`<app>/backend`, `<app>/ui`, `plataforma/core`, etc.). Cuando esté definitiva, se moverá a un doc propio.

Documentos relacionados:

- [PROYECTO_CONTEXTO.md](PROYECTO_CONTEXTO.md) — estado actual y prioridad vigente
- [AGENTS.md](AGENTS.md) — reglas operativas para agentes
- [arquitectura/ARQUITECTURA.md](arquitectura/ARQUITECTURA.md) — flujo de red, componentes Docker, modelo de comunicación
- [arquitectura/PROXY_INVERSO.md](arquitectura/PROXY_INVERSO.md) — detalle del proxy
- [arquitectura/CONTRATO_APPS.md](arquitectura/CONTRATO_APPS.md) — contrato que toda app debe cumplir
- [estandares/ESTANDARES.md](estandares/ESTANDARES.md) y [estandares/DESIGN_SYSTEM.md](estandares/DESIGN_SYSTEM.md)
- [operacion/deploy/GUIA_DEPLOY.md](operacion/deploy/GUIA_DEPLOY.md) — cómo se despliega
- [changelog/](changelog/) — bitácora completa del proyecto

---

## 1. Visión

Monstruo es el ERP/CRM/operativo + motor de integración interno de Telconsulting. Reemplaza herramientas externas (mesa de ayuda, gestión de proyectos, planificación de tareas) y unifica los silos de información (Laudus, Parrotfy, Buk, bancos, Zabbix) en una sola fuente de verdad con automatización, auditoría y evidencia.

No es un iPaaS comercial. Es una plataforma propia, modular, con una app por dominio funcional.

## 2. Principios no negociables

### 2.1 Estabilidad y rollback

- Cambios pequeños.
- Cada release con plan de rollback.
- Migraciones DB siempre reversibles, o forward-only con backup `pg_dump` previo y plan documentado.

### 2.2 Trazabilidad y auditoría

- Todo cambio de negocio importante deja rastro: quién / cuándo / qué / por qué / desde dónde.
- Evidencias firmadas con hash + metadata + cadena de custodia para auditoría ISO 27001.

### 2.3 Seguridad por defecto

- RBAC estricto en backend.
- La UI es solo conveniencia. La autorización real vive en el API.
- Auditoría obligatoria para acceso a datos sensibles (CRM, finanzas, evidencias).

### 2.4 Modularidad real

- Una app por dominio funcional. Cada app es autocontenida y se puede levantar/desplegar por separado.
- Comunicación entre apps solo por API HTTP a través del gateway. Cero imports cruzados.
- Lo genuinamente transversal (auth, db, jobs, notifs) vive en `plataforma/core/`.

### 2.5 Separación DEV/PROD

- Rama `dev` y rama `main`. No se promueve a `main` sin autorización explícita.
- Nombres de stack, env files y compose projects nunca se cruzan entre entornos.
- Detalle del contrato canónico en [PROYECTO_CONTEXTO.md](PROYECTO_CONTEXTO.md) y [operacion/deploy/GUIA_DEPLOY.md](operacion/deploy/GUIA_DEPLOY.md).

## 3. Protocolo de trabajo

Cada tarea cierra este ciclo:

1. **Plan** breve.
2. **Confirmación** del usuario.
3. **Ejecución** acotada al scope.
4. **Verificación** con evidencia (PASS/FAIL).
5. **Cierre** con resumen técnico.

Reglas:

- Una tarea a la vez.
- No meter cambios fuera de scope antes de cerrar la tarea solicitada.
- Si una decisión depende de comportamiento multiusuario (cache-bust, locks, rate-limit), se marca como "Producción" y no se fuerza en DEV.

## 4. Cumplimiento Chile (resumen)

| Marco | Aplicación práctica en Monstruo |
|---|---|
| Ley 21.719 (Protección de Datos Personales) | Datos personales en CRM/ticketera con consentimiento, derecho de acceso/borrado, retención configurada |
| Ley 21.663 (Ciberseguridad) | Logs de seguridad, control de accesos, auditoría de cambios críticos |
| Facturación electrónica DTE (SII) | Integración Laudus para emisión, espejo de respuestas, mapeo de estados |
| ISO/IEC 27001 (objetivo) | Cadena de custodia de evidencias, hash de artefactos, retention policy, control de accesos auditado |

Nivel detalle de cada control: ver `arquitectura/CONTRATO_APPS.md` y módulos de auditoría en `plataforma/core/audit.py`.

## 5. RBAC y autenticación

### Modelo

Entidades:

- `users`
- `roles`
- `permissions` (scopes por dominio)
- `role_permissions`
- `user_roles`

### Permisos por dominio

Convención `<dominio>:<acción>`. Ejemplos:

- `erp:read`, `erp:write`, `erp:reconcile`
- `crm:read`, `crm:write`
- `bodega:read`, `bodega:write`, `bodega:ai`
- `tickets:read`, `tickets:write`, `tickets:compliance`
- `gta:read`, `gta:write`
- `pmo:read`, `pmo:write`
- `admin.settings`, `admin.prompts`
- `ai:use`, `ai:train`, `ai:audit`

### Reglas duras

- Nadie hereda permisos por UI.
- Backend valida siempre. Si el frontend no muestra un botón pero la sesión no tiene permiso, el API responde 403 igual.
- Auditoría obligatoria en accesos a datos sensibles.

Login único por gateway, sesión heredada por todas las apps.

## 6. Apps del sistema

### Estado a 2026-05-05

| App | Estado | Notas |
|---|---|---|
| **gateway** | ✅ Producción | Punto de entrada, auth, RBAC, proxy a apps internas, shell UI |
| **ticketera** | ✅ Producción + mantención | Mesa de ayuda interna, flujos workflow + SLA + compliance |
| **gta** | 🟢 **Prioridad actual** | Gestión de Tareas Automatizadas (procesos cross-área) |
| **crm** | ✅ Producción | Clientes, contactos, leads, oportunidades, espejo Laudus |
| **erp** | ✅ Producción | Facturación DTE, conciliación bancaria, cobranza |
| **bodega** | ✅ Producción | Catálogo, stock, movimientos, IA dedupe/categorización |
| **fundacion** | ✅ Producción | Módulo Fundación (sedes, planificación, scope por usuario) |
| **pmo** | 🟡 Fase 1 | Gestión de proyectos (dashboard + modelo de datos) |
| **ia** | 🟡 En desarrollo | ULTRON central + agentes por módulo (parcialmente operativo) |
| **zabbix** | 🟡 Integrado | Monitoreo. Auto-creación de tickets aún no implementada |

### Especificación por app

La especificación funcional de cada app vive en `<app>/docs/` cuando existe. Ejemplos vigentes:

- [gta/docs/](../../gta/docs/) — ARQUITECTURA + API + README hub
- [ticketera/docs/](../../ticketera/docs/)
- [gateway/docs/](../../gateway/docs/)

Las apps sin `docs/` propia comparten el contrato común documentado en [arquitectura/CONTRATO_APPS.md](arquitectura/CONTRATO_APPS.md).

## 7. Plataforma compartida (`plataforma/core/`)

Solo lógica genuinamente transversal:

- `db.py`, `migrations.py` — base de datos, schemas, DDL
- `security.py`, `auth_service.py`, `deps.py` — auth, RBAC, dependencies FastAPI
- `config.py`, `env_loader.py` — settings, carga de entornos
- `middleware.py`, `web.py` — HTTP middlewares y utilidades web
- `jobs_engine.py` — motor de jobs persistente con retry/DLQ
- `email.py`, `email_integration.py` — envío y polling de correo
- `google_chat.py` — notificaciones Google Chat
- `notifications.py` — sistema de notificaciones in-app
- `audit.py`, `audit_decorator.py` — auditoría con decorador
- `ai/` — bridge a IA local (OpenAI-compat) + políticas y prompts

**Lo específico de una app vive en la app**, no acá. Si aparece tentación de poner `<algo>_service.py` en `core/`, primero confirmar que sea usado por más de una app o cancelar.

## 8. Roadmap (estado)

### Gates históricos

| Gate | Alcance | Estado |
|---|---|---|
| A | Plataforma base (auth + RBAC + jobs + auditoría) | ✅ |
| B | ERP + Conciliación bancaria | ✅ |
| C | Bodega + IA | ✅ |
| D | Ticketera | ✅ |
| E | GTA + PMO Fase 1 | 🟡 (GTA en desarrollo activo, PMO Fase 1 ✅) |
| F | Producción multi-app + observabilidad | 🟡 |

### Pendientes activos

- GTA: completar features y test coverage (ver [gta/docs/ARQUITECTURA.md](../../gta/docs/ARQUITECTURA.md), sección Pendientes).
- Ticketera: bug fixes y deuda residual de migraciones.
- Migraciones PROD: confirmar que apps en `192.168.60.5` escuchen en `9001/9005/9006` (proxy ya enruta ahí).

### Pendientes diferidos

- Zabbix → auto-ticket (EPIC 14 archivado).
- Preventa, Reportería, Project-to-Cash, Sincronización Comercial: ver [archive/EPICS_FUTUROS.md](archive/EPICS_FUTUROS.md). Reactivar si vuelve a ser prioridad.

## 9. Cómo se actualiza esta guía

- Cambios de **reglas o protocolo** (secciones 2-5): actualizar acá.
- Cambios **operativos** (deploy, contrato canónico): en `operacion/deploy/GUIA_DEPLOY.md` o `PROYECTO_CONTEXTO.md`.
- Cambios de **una app específica**: en `<app>/docs/` o su `README.md`, no acá.
- **Hitos ejecutados**: en [changelog/](changelog/) (mes-año correspondiente), nunca acá.
- **Estructura del repo**: pendiente. Cuando se estabilice, doc propio.

Nunca volver a hacer un doc monstruo de 2000+ líneas mezclando reglas + bitácora + estructura + spec por app + roadmap + EPICs futuros. Cada cosa en su lugar.
