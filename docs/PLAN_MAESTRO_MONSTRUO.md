PLAN MAESTRO MONSTRUO

Proyecto: MONSTRUO (Telconsulting)
Versión: v1.1
Fecha: 2026-02-14
Autoría: Juan + IA (plan operativo y arquitectura)
Propósito del documento: ser la única guía oficial de construcción. Si el agente propone algo que no calza con esto, se rechaza.

0) Cómo se usa este plan (modo “contrato” para humanos y para IA)

---

0.1 Reglas de uso

Este plan manda. Si hay conflicto entre “ideas” y este plan, gana el plan.

Una tarea por ciclo: cada entrega debe terminar un hito pequeño con verificación (no “10 cosas”).

Cada tarea debe tener:

Objetivo (1 frase)

Scope (qué sí) y Out-of-scope (qué no)

Artefactos (archivos/tablas/endpoints)

Criterio de aceptación (pass/fail)

Verificación (comandos/chequeos)

Rollback

No se avanza si no hay verificación.

Toda decisión que dependa de multiusuario (cache-bust, sesiones, locks, rate-limit, etc.) se marca como “Producción” (no se fuerza en Lab).

0.2 Protocolo de trabajo recomendado para cualquier IA

Ciclo estándar (SIEMPRE):

PLAN (lista corta, no ejecutar)

CONFIRMACIÓN humana (tú)

EJECUCIÓN (patch/diff o cambios acotados)

VERIFICACIÓN (tests + checks + smoke)

CIERRE (qué cambió + bitácora + siguiente paso)

Esto no es “burocracia”: es el antídoto contra agentes que se dispersan.

0.3 “Guardian” conceptual (para evitar alucinaciones)

Aunque lo implementes o no como servicio, el concepto es obligatorio:

No se acepta una entrega si:

Cambia más archivos que los autorizados

Cambia más líneas que el límite

No tiene verificación

No cumple políticas (nombres prohibidos, rutas raras, etc.)

No cumple políticas (nombres prohibidos, rutas raras, etc.)

No actualiza la bitácora (si aplica)

**REGLA DE ORO DE BACKUPS:**
Los backups NO se guardan dentro del proyecto (`/srv/monstruo`).
Se deben mover a la carpeta externa `/srv/monstruo_old/` (El Museo) para mantener el repositorio limpio.

0.4 Bitácora de avances recientes (resumen corto)

- 2026-02-14: Gobernanza documental reforzada: `PROMPT_CHAT_UNIVERSAL.md` actualizado a versión vigente (bootstrap + matriz anti-cruce DEV/PROD + carga obligatoria de `ESTANDARES.md` y allowlists `.README.md`).
- 2026-02-14: Ticketera: respuesta por correo desde detalle de ticket, con intento de mantener hilo (headers `In-Reply-To`/`References`) y registro de salida/entrada en historial.
- 2026-02-14: Ticketera: control anti-duplicado de correos salientes por reintentos de UI (ventana de dedupe + marcador `outgoing_pending`).
- 2026-02-14: Ticketera: formato de código actualizado a `TK-DD-MM-YYYY-NNNN` con compatibilidad de parser para formatos previos en correo entrante.
- 2026-02-14: Entorno DEV: limpieza total de ticketera para partir de cero (`tickets`, `ticket_comments`, `ticket_notifications`, `ticket_emails`, `ticket_attachments`) y reset de `current_load` en `user_specialties`.
- 2026-02-01: Bodega UX afinada: rutas de categorías homogéneas en inventario (sin duplicar padres), catálogo con selección múltiple + asignación masiva, búsqueda y conteos de árbol corregidos.
- 2026-01-29: Bodega/Catálogo con multi-categoría (tabla `cat_item_categories`) y filtro por categoría que incluye subcategorías.
- 2026-01-29: UI Bodega: búsqueda case-insensitive en inventario, Kardex en drawer derecho, sidebar persistente entre módulos.
- 2026-01-29: Catálogo: carga de items (Laudus), vista catálogo funcional, normalización visual en minúsculas.
- 2026-01-29: Categorías reducidas a EQUIPOS/MATERIALES (base) para consolidación inicial.
- 2026-01-29: Integración Laudus aplicada a stock (sync + apply_stock) y fuente real en Bodega.
- 2026-01-29: Refinamiento de Jerarquía: Carpetas "Sin Asignar" ocultas en Equipos/Materiales + Limpieza de duplicados.
- 2026-02-09: **Infraestructura Profesional (CI/CD)**: Implementación de GitHub Actions con Self-Hosted Runner. Despliegue automático a producción al hacer push a `main`. Servidor protegido (no se edita directo).
- 2026-02-09: **ERP/Bancos**: Integración real con dispositivo físico (ws-scrcpy), streaming de pantalla funcional y sesión persistente.
- 2026-02-09: **UI Global**: Estandarización de headers y switcher de ambiente (Lab/Prod) unificado en topbar.


0.5 Flujo de Despliegue (CI/CD / GitHub Actions) ✅ IMPLEMENTADO

**PROTOCOLOS OBLIGATORIOS PARA CUALQUIER AGENTE:**
1.  **NO TOCAR SERVIDORES:** Prohibido entrar por SSH a editar código en producción (`/srv/monstruo`).
2.  **RAMA MAIN PROTEGIDA:** La rama `main` despliega a producción automágicamente. **NUNCA** hacer push directo a `main` sin autorización explícita.
3.  **FLUJO DE TRABAJO:**
    *   Crea una rama `feature/nombre-tarea`.
    *   Haz tus cambios localmente.
    *   Push a GitHub: `git push origin feature/nombre-tarea`.
    *   **Solicita revisión:** El usuario (humano) debe aprobar y hacer el merge a `main` en GitHub.
    *   Solo tras el merge, el runner de GitHub Actions despliega.

**Ciclo de Vida:**
1.  **Local (Dev):** Tu entorno de trabajo (WSL). Aquí rompes y arreglas.
2.  **Pull Request (Review):** Subes a GitHub. El humano revisa.
3.  **Producción (Live):** Al mergear a `main`, el runner actualiza el servidor.

**Comando permitido para Agentes:**
```bash
git checkout -b feature/nueva-funcionalidad
# ... cambios ...
git push origin feature/nueva-funcionalidad
# NOTIFICAR AL USUARIO PARA MERGE
```

0.6 Prioridad Operativa Vigente (desde 2026-02-14)

**MANDATO DE NEGOCIO:**
- **EPIC 11 (Ticke-Tera) pasa a Prioridad Máxima Absoluta.**
- Objetivo: **reemplazar la mesa externa actualmente contratada** por una solución interna de nivel profesional.
- Hasta cerrar EPIC 11 en estándar productivo, **no se abre desarrollo neto** de EPIC 12+ (excepto incidentes críticos o bloqueos técnicos de infraestructura/seguridad).

**Definición de "100% profesional" para dar por cerrado EPIC 11 (Go/No-Go):**
- Estabilidad: 0 errores 500 en flujos críticos (`crear`, `asignar`, `responder`, `listar`, `detalle`).
- Correo operacional completo: reply en hilo + adjuntos + historial legible entrada/salida.
- Anti-duplicado robusto: reintentos de UI/API no generan doble envío.
- Separación DEV/PROD validada y automatizada (SMTP, credenciales, jobs, URLs base).
- Suite E2E ticketera verde en CI (`create -> reply -> dedupe -> incoming thread match`).
- UX de operación fluida (sin bloqueos perceptibles en navegación y cambio de vistas).

0.7 Gobernanza de Agentes (obligatoria desde 2026-02-14)

Archivo canonico de reglas para agentes en DEV:
- `.agent/rules/monstruo-dev-reglas.md`
- `AGENTS.md` (bootstrap para agentes compatibles)

Estandar unico:
- Se elimina la regla legacy y queda un solo archivo canonico de reglas.

Regla operativa:
- Ningun agente ejecuta cambios sin haber cargado `monstruo-dev-reglas.md`.
- Ninguna entrega se considera valida si contradice ese archivo, el Plan Maestro o el Proyecto Contexto.

Efecto en el trabajo diario:
- Se fuerza foco en EPIC 11 (Ticketera) hasta cumplir Go/No-Go profesional.
- Se evita cruce DEV/PROD por norma explicita para ramas, env files, jobs y credenciales.


---

1) Visión y alcance
1.1 Visión

MONSTRUO es el ERP/CRM operativo + motor de integración para Telconsulting: integra silos (Laudus, Parrotfy, Buk, bancos, Jira, Zabbix, etc.) en una fuente de verdad con automatización, auditoría y evidencia.

1.2 ¿Esto es iPaaS o no?

iPaaS (Integration Platform as a Service) se define como un conjunto de servicios cloud para desarrollar/ejecutar/gobernar flujos de integración entre apps y datos (on-prem + cloud).

Lo que tú estás construyendo es:

Un ERP/CRM (producto final)

un motor de integración interno (estilo iPaaS “privado” dentro de tu plataforma)

Si lo despliegas y lo ofreces como plataforma para integrar terceros (con conectores, gobernanza, monitoreo de flujos, etc.), se parece a un iPaaS; si queda como middleware interno, es “Integration Hub / Integration Engine”.

Conclusión práctica: diseña la capa de integraciones “como iPaaS”, aunque el producto final sea “ERP/CRM + Operations OS”.


---

2) Principios NO negociables
2.1 Estabilidad y rollback

Cambios pequeños.

Cada release con rollback.

Migraciones DB siempre reversibles (o con backup + forward-only explicitado).

2.2 Trazabilidad y auditoría

Todo cambio de negocio importante deja:

quién / cuándo / qué / por qué / desde dónde

Evidencias con hash + metadata + cadena de custodia (nivel auditoría).

2.3 Seguridad por defecto

RBAC estricto en backend.

UI solo es “conveniencia”; la seguridad real vive en el API.

2.4 Modularidad real

Monolito modular ahora (rápido y controlable).

Diseñado para extraer módulos a servicios si crece.


---

3) Estructura de Módulos (Los 8 Pilares de MONSTRUO)

Para mantener la simplicidad y el control, el sistema se divide en 8 módulos funcionales en el Frontend:

1.  **Dashboard (Operaciones):** Vista global, KPIs inter-módulos, alertas de salud del sistema.
2.  **ERP & Finanzas:** Centraliza Facturación, Pagos, Conciliación Bancaria y Cobranza.
3.  **CRM (Clientes):** Directorio único, Ficha Legal (Compliance), Bitácora Comercial y Contactos.
4.  **Bodega (WMS):** Catálogo maestro, Control de Stock, Movimientos y Evidencias.
5.  **TKs (Ticketera):** Mesa de ayuda interna, automatización de flujos y SLAs.
6.  **IA (ULTRON):** Asistente centralizado, análisis predictivo y automatización cognitiva.
7.  **Zabbix (Monitoreo):** Integración directa de infraestructura y alertas de red.
8.  **Configuración:** Gestión de Auth/RBAC, Triggers, Prompts y Feature Flags.


---

4) Arquitectura objetivo (Blueprint)
4.1 Estilo recomendado

Monolito modular (FastAPI) + jobs/colas + adaptadores de integración.

Por qué:

Rápido ahora, controlable.

Mantienes límites por módulo (carpetas, routers, schemas, servicios).

Puedes extraer microservicios después sin reescribir todo.

4.2 Capas del backend

API Layer (FastAPI Routers)

/api/auth/*

/api/erp/*

/api/crm/*

/api/bodega/*

/api/tickets/*

/api/proyectos/*

/api/preventa/*

/api/reportes/*

/api/integraciones/*

/api/ai/*

Application Services

Reglas de negocio (sin dependencias web)

Orquestación transaccional

Domain Model

Entidades, invariantes, validaciones

Infrastructure Layer

DB

Integraciones externas (Laudus/Parrotfy/Buk/Jira/Zabbix/Bancos)

Cola de jobs

Files/Evidencias

Observability

logs estructurados

métricas

auditoría

4.3 Frontend modular
HTML + JS vanilla estilo “Neon Command”.
Estructura física: `/modulos/${modulo}/${modulo}.html`.
Solo existen 8 carpetas funcionales bajo `/modulos/` (más `_compartido` y `login`).
Una “shell” común: sidebar + topbar + notifications.
4.3.1 Estándar Visual ERP (Gold Standard)
El módulo ERP define la línea gráfica oficial que deben seguir todos los nuevos módulos.
Elementos clave:
- Layout: Pestañas de navegación interna (`.tab-bar` + `.tab-btn`) para separar vistas (Resumen, Detalle, Config).
- Headers: `h2` con `letter-spacing: -0.5px` y subtítulos explicativos.
- KPIs: Tarjetas superiores (`.kpi-card`) con valores grandes y etiquetas uppercase.
- Tablas: Estilo `.erp-table` con filas separadas (`border-spacing`), hover sutil y bordes redondeados.
- Animaciones: Transiciones suaves (`fadeIn`) al cambiar de pestaña.
- Paleta: Uso activo de variables CSS `--neon`, `--panel-strong`, `--text-soft`.
Cualquier desviación de este estándar se considera deuda de UX.

4.4 Base de datos

Local (Lab actual): PostgreSQL (idealmente con Docker Compose) para simular producción desde ya.

Producción: PostgreSQL en servidor.

SQLite queda solo para pruebas rápidas o prototipos aislados.

Regla: el esquema y el código deben ser agnósticos al motor (usar DB_URL y migraciones).

Estado actual (2026-01-29): se adopta PostgreSQL local con Docker y migración desde SQLite.

Herramientas activas:
- docker-compose.yml (PostgreSQL local)
- ops/herramientas/migrate_sqlite_to_postgres.py (migración SQLite -> PostgreSQL)


---

5) Modelo de cumplimiento Chile (alto nivel, sin “legalese” inútil)
5.1 Protección de datos personales

Chile tiene una modernización fuerte con la Ley 21.719; según BCN, se publicó 13-dic-2024 y entra en vigencia el 1-dic-2026.

En el diseño del CRM/IA/Evidencias asume desde ya:

Registro de finalidades

Minimización de datos

Control de acceso granular

Auditoría de acceso a datos sensibles

Ciclo de vida / retención / eliminación controlada

Nota realista: cuando estés cerca de producción, esto se valida con asesoría legal, pero la arquitectura debe nacer “compliance-ready”.

5.2 Ciberseguridad

La Ley 21.663 (Ley Marco de Ciberseguridad) crea institucionalidad como ANCI, CSIRT, etc., publicada 8-abr-2024.
Implicancia para MONSTRUO:

Gobernanza y gestión de incidentes

Evidencia y trazabilidad en incidentes

Reportabilidad (en organizaciones que caigan en obligaciones específicas)

5.3 Facturación electrónica (SII / DTE)

A nivel operativo, SII guía que para anular una factura electrónica se emite una Nota de Crédito Electrónica de anulación (generar, firmar y enviar al SII).
Y para anular una Nota de Crédito, se emite una Nota de Débito de anulación.

Implicación de diseño:

Los DTE no se “borran”: se corrigen/anulan por documentos relacionados (NC/ND) con trazabilidad.


---

6) Diseño de seguridad y acceso (LOGIN + RBAC)
6.1 Objetivo

Un login único. Cada usuario ve y hace solo lo autorizado. Si intenta URL directo → 403.

6.2 Especificación RBAC

Entidades:

users

roles

permissions (o scopes)

role_permissions

user_roles

Permisos por dominio, ejemplo:

erp.read, erp.write, erp.reconcile

crm.read, crm.write

bodega.read, bodega.write, bodega.ai

tickets.read, tickets.write, tickets.jira

proyectos.read, proyectos.write

preventa.read, preventa.write

admin.settings, admin.prompts

ai.use, ai.train, ai.audit

6.3 Reglas duras

Nadie “hereda” permisos por UI.

Back-end valida siempre.

Auditoría para accesos a datos sensibles (CRM, finanzas, evidencias).


---

7) Núcleo de plataforma (Core Platform)

Este core es lo que evita que el sistema se vuelva spaghetti.

7.1 Configuración del sistema

Objetivo: una pestaña “Configurar aplicación” real y segura.

Incluye:

Feature flags por módulo

Umbrales (ej. conciliación auto >= 0.85)

Parámetros de integraciones (sin exponer secretos)

Plantillas de notificaciones

Reglas de trigger (detonantes)

Gestión de prompts/IA (con permisos)

7.2 Auditoría

Tabla audit_log (append-only ideal).

Eventos auditables mínimos:

CRUD de facturas/pagos/conciliaciones

cambios en proveedores y precios

cambios de catálogo

cambios de permisos/roles

aceptación/rechazo de sugerencias IA

creación/cierre de tickets

cambios de alcance de preventa

7.3 Notificaciones

Canal interno: “campanita” en UI.

Canales externos (etapa posterior): email, Teams/Slack si aplica.

7.4 Motor de reglas (Triggers)

Esto es clave para tu visión (tickets automáticos, etc.)

Diseño:

trigger_definitions (qué evento dispara)

trigger_actions (qué acción se ejecuta)

trigger_runs (registro de ejecuciones, estado, error)

Ejemplos de triggers:

“Cierre de negocio en CRM” → crear ticket “Onboarding/Entrega”

“Zabbix alerta severity HIGH” → crear incidente + notificar

“Conciliación fallida por X días” → crear ticket cobranza

“Discrepancia Parrotfy vs Laudus” → ticket + tarea catálogo


---

8) Motor de integraciones (tu “iPaaS interno”)
8.1 Objetivo

Conectar sistemas sin que el código principal se llene de if/else y scripts sueltos.

8.2 Conceptos base

Connector: adaptador a un sistema (Laudus/Parrotfy/Buk/Jira/Zabbix/Banco).

Pipeline: secuencia de pasos (extract → transform → load).

Job: ejecución concreta con logs, estado, reintentos.

Idempotencia: correr dos veces no rompe nada.

DLQ (dead-letter queue): lo que falla no se pierde; queda para revisión.

8.3 Tipos de integración

Pull scheduled (cron):

sync facturas

sync stock

Webhook/event-driven

Zabbix event

Jira issue updates

Manual / operador

subir cartola banco

importar Excel (dropzone) para Buk plan B

8.4 Estándares

Cada conector tiene:

healthcheck

rate_limit

retry_policy

error_mapping (cómo se interpreta un 500/timeout)

Cada pipeline debe producir:

resumen (contadores)

errores con categoría

evidencia (payload hash, timestamps)


---


---

9) Especificación módulo ERP (Chile-ready)
9.1 Objetivo del ERP

Cumplir operación real: facturar, comprar, pagar, conciliar, y soportar normativa Chile (DTE y trazabilidad).

9.2 Submódulos ERP
A) Maestro

Clientes (también CRM)

Proveedores

Productos/Servicios (integrado con Bodega/Preventa)

Centros de costo (para proyectos/rentabilidad)

B) Ventas / Facturación

Cotización (opcional si preventa cubre)

Orden de venta

Factura

Nota de crédito

Nota de débito

Estado tributario (pendiente, aceptado, rechazado, etc.)

Envío al cliente (email)

Integración con CRM (oportunidad → factura)

Regla de diseño DTE: no hay “editar factura emitida”: se emite corrección (NC/ND) con referencia.

C) Compras

Requisición interna

Orden de compra (OC)

Recepción conforme

Factura proveedor

Pago proveedor

D) Pagos y cobranza

Registro de pagos (manual y por integración)

Cobranza (gestión + automatización de recordatorios)

Integración con Ticketera

E) Conciliación bancaria

Entrada:

Cartola (CSV/OFX) manual o integración
Proceso:

Normalización

Matching (referencia/fecha/monto/descripción)
Salida:

conciliación automática con confianza

cola de revisión manual para casos dudosos

tickets por casos “atrasados”

9.3 Conciliación bancaria: algoritmo recomendado (práctico)

Normaliza transacciones:

fecha, monto, moneda, glosa, identificadores

Genera candidatos:

match por referencia exacta (si existe)

match por monto exacto + ventana de fecha

match fuzzy por tokens en glosa vs cliente/factura

Score de confianza:

exact ref: 1.0

monto + fecha: 0.85

fuzzy: 0.65–0.80

Umbrales configurables:

= 0.90 auto-concilia

0.75–0.89 propone (humano decide)

< 0.75 crea ticket/revisión

9.4 UI mínima ERP (primera versión usable)

Panel Finanzas:

Aging

Facturas vencidas

Conciliación pendiente

Pantalla facturas (listado + detalle)

Pantalla cartolas (import + revisión)

Pantalla conciliación (matching UI)

Proveedores + pagos

9.5 Criterios de aceptación ERP (DoD)

No se puede “borrar” una factura emitida (solo NC/ND referenciada).

Toda conciliación deja audit trail.

Importar cartola no duplica transacciones (idempotencia).

Cierre financiero mensual genera reporte.


---

10) Especificación módulo CRM (Chile + operación real)
10.1 Objetivo CRM

Gestionar clientes, oportunidades, actividades, y trazabilidad comercial sin romper compliance.

10.2 Submódulos CRM

Clientes (Account)

Contactos

Leads

Oportunidades

Pipeline stages

Actividades (llamadas, reuniones, emails)

Documentos (propuestas, contratos, anexos)

Consentimientos y finalidades (compliance)

10.3 Integraciones CRM

Email ingestion (lectura y clasificación)

Preventa: oportunidad → configuración → propuesta

Ticketera: cierre negocio → ticket onboarding

10.4 Criterios de aceptación CRM

RBAC: bodegas NO ve CRM si no está autorizado.

Acceso a datos sensibles auditado.

Export de datos por cliente (para solicitudes internas de compliance).


---

11) Especificación Bodega (Inventario + Catálogo + IA)
11.1 Objetivo

Ordenar inventario, catalogar, encontrar similares, deduplicar, y mantener normativa interna/Chile cuando aplique.

11.2 Componentes Bodega

Catálogo maestro (producto “canónico”)

Items de inventario (stock real)

Movimientos (entrada/salida/ajustes)

Ubicaciones

Proveedores preferidos

Evidencias (fotos, guías, etc.)

11.3 IA de Bodega (práctica y segura)

Funciones IA:

Similaridad (texto + atributos)

Duplicados (sugerencia)

Clasificación taxonómica (categorías)

Normalización nombres (estándar interno)

Alertas de inconsistencia (ej. stock raro)

Reglas IA:

Toda sugerencia tiene:

confidence

explicación corta

propuesta de acción

Nunca ejecuta cambios masivos sin “modo revisión humana”.

Cada aceptación/rechazo alimenta dataset de mejora (log).

11.4 Criterios de aceptación Bodega

Dedupe no borra: propone merge.

Merge guarda trazabilidad: “producto A absorbido por B”.

Stock snapshot consistente y recuperable.

Búsqueda rápida (debounce, index, etc.)


---

12) Ticketera (interna) + Jira (externa)
12.1 Objetivo

Unificar gestión de casos internos y sincronizar con Jira cuando corresponda.

12.2 Tipos de ticket

Operación interna (finanzas, bodega, crm)

Incidente (monitoring)

Proyecto (entregables)

Preventa (cotización/configuración)

Integración (errores de APIs externas)

12.3 Características clave

Estados: NEW → TRIAGE → IN_PROGRESS → BLOCKED → DONE → CLOSED

SLA por tipo y severidad

Kanban por equipo

Auto-escalamiento

12.4 Integración Jira (mínimo viable)

Tabla mapping:

ticket_id ↔ jira_issue_key

Sync:

crear en Jira cuando el ticket sea “externo”

actualizar estados y comentarios

adjuntar evidencias (si política lo permite)

12.5 Triggers que DEBEN existir

Zabbix High → Incidente + notificación

Conciliación fallida N días → ticket finanzas

Discrepancia inventario → ticket bodega

Cierre oportunidad CRM → ticket onboarding/proyecto


---

13) Gestión de Proyectos (JP) [ESTADO: IMPLEMENTADO FASE 1 - 2026-01-31]
13.1 Objetivo

Que el JP pueda:

asegurar reuniones internas y con cliente

controlar costos diarios (HH + viáticos + combustible/vehículo)

tener “rentabilidad anticipada”

automatizar entregables hacia otras áreas

usar IA para revisar faltantes y riesgos

13.2 Submódulos JP

Proyectos

ficha proyecto

cliente asociado

alcance

hitos

Reuniones

agenda

asistentes

acuerdos

integración con resúmenes IA (cuando exista)

HH y costos diarios

timesheet (por persona, por día)

gasto vehículo (km, combustible, peajes)

viáticos

Entregables inter-área

solicitud a bodega (equipos)

solicitud a redes (IP, ubicaciones)

prevención (documentos, permisos, etc.)

Riesgos y bloqueos

checklist antes de visita cliente

dependencias y responsables

13.3 IA para JP (asistente real, no “chat bonito”)

“Checklist IA”:

antes de reunión cliente, lista faltantes

genera borradores de correo (pero no envía sin aprobación)

“Extracto IA” de reuniones:

acuerdos

tareas asignadas

próximos hitos

“Control IA”:

si falta un documento crítico → crea ticket


---

14) Preventa (configurador + plantillas + proveedores)
14.1 Objetivo

Que preventa cotice rápido, consistente, y con reglas de alcance claras según lo contratado.

14.2 Componentes

Plantillas pre-ensambladas

Ej: “Starlink con IP pública”

Componentes fijos + variables (soporte, extras)

Configurador dinámico

preguntas encadenadas

agrega/quita componentes

define servicios (monitoreo, ciberseguridad, 24/7, admin)

Motor de reglas de alcance

“si cliente compra A+B → alcance incluye X”

“si no compra 24/7 → soporte horario hábil”

Recomendador de proveedores

scoring por:

precio

stock

plazo entrega

condiciones pago (30 días suma “estrellas”)

confiabilidad histórica

Comparador

“mejor valor” ≠ “más barato”

14.3 Outputs del módulo Preventa

propuesta interna (costeo)

propuesta cliente (alcance + exclusiones)

paquete para ERP (para facturar)

paquete para bodega (materiales)

paquete para proyectos (plan de ejecución)


---

15) Reportería (Gerencia / Clientes / Operación)
15.1 Objetivo

Convertir MONSTRUO en “tablero de mando” de Telconsulting.

15.2 Reportes mínimos por audiencia
Gerencia

Cashflow (proyectado y real)

Aging + top deudores

Rentabilidad por proyecto (early warning)

Incidentes y SLA (tendencias)

Ventas (pipeline y cierre)

Operación

Bodega: stock crítico, rotación, pendientes de catálogo

Ticketera: backlog, SLA, incidentes masivos

Integraciones: jobs fallidos, latencia, APIs con errores

Clientes (opcional por contrato)

SLA y tickets

avances proyecto

evidencias (si aplica)


---

16) Zabbix (monitoreo → ticket automático)
16.1 Objetivo

Que Zabbix sea un “sensor” del mundo real:

si cae algo → ticket

si es masivo → incidente mayor

notifica a quien corresponde

16.2 Clasificación de eventos

Severity mapping:

Informational → log

Warning → ticket normal

High → incidente

Disaster → incidente mayor + escalamiento

16.3 Anti-ruido

dedupe por fingerprint (host+trigger+window)

agrupación (incidente padre + subeventos)


---

17) IA Telconsulting (ULTRON central + IA por módulo)
17.1 Arquitectura IA

ULTRON central:

visión global

políticas transversales

decide escalamiento humano

Agentes por módulo:

Bodega AI

Finanzas/ERP AI

CRM AI

JP AI

Preventa AI

Ticketera AI

17.2 Política de “colisión”

Caso: Bodega AI sugiere algo que afecta costos y ERP AI tiene política de aprobación.

Regla: si una IA rompe la política de otra, ULTRON:

bloquea acción

crea ticket/alerta

pide aprobación humana

17.3 Memoria y conocimiento

Knowledge base corporativa (docs, perfiles, políticas, playbooks).

Indexación y RAG.

Auditoría de prompts (sin exponer datos sensibles fuera).

17.4 Salidas estructuradas (para controlar al agente)

Si trabajas con Gemini, usa “function calling” o forcing mode para que responda en JSON (y no se vaya por la tangente). Google documenta modos como ANY para forzar tool-calls/estructura y el uso de schemas tipo OpenAPI subset.


---

18) Evidencias (técnico + cumplimiento)
18.1 Objetivo

Trazabilidad fuerte: qué evidencia, quién la capturó, cuándo, dónde, integridad (hash), y relación con tickets/proyectos/facturas.

18.2 Modelo mínimo

Archivo (path interno)

SHA256

metadata (GPS, dispositivo, uploader)

relación a entidad (ticket/proyecto/OC/etc.)

retención configurada (por módulo/cliente)

18.3 Cadena de custodia

No se reemplaza evidencia: se versiona.

Toda descarga/visualización relevante se audita (si es crítico).


---


---

19) Roadmap “bestial” en formato de EPICS + gating

La clave: no es “orden estricto”, es dependencias + puertas (gates).
Puedes reordenar, pero no saltarte gates.

19.1 Gates (puertas obligatorias)

---
GATE A — Plataforma Base Operable

Se considera logrado cuando:

Auth/RBAC funcionando (403 real)

Auditoría básica

Settings base

Framework de jobs (aunque sea simple)

Estructura modular de repo ordenada

Smoke tests (mínimo)


---
GATE B — ERP mínimo “Invoice to Cash”

Facturas

Pagos

Import cartola

Conciliación (manual + auto sugerida)

Report básico finanzas


---
GATE C — Bodega + Catálogo con IA asistida

Catálogo maestro

Dedupe sugerido

Categorización sugerida

Aceptar/rechazar con audit


---
GATE D — Ticketera + Automatizaciones

Tickets + SLA + Kanban

Triggers desde ERP/CRM/Bodega

Integración Jira POC

**Prioridad vigente:** cierre total de EPIC 11 antes de expandir alcance a EPIC 12+.


---
GATE E — Proyectos + Preventa

Plantillas preventa + configurador

Proyectos con HH y gastos

Report rentabilidad temprana


---
GATE F — Observabilidad + Producción Multiusuario

Hardening real

Versionado estáticos / cache-bust

Métricas y alertas

Backups/restore probado

19.2 Backlog por EPIC (nivel “Dios”, pero accionable)

Te dejo un backlog por épicas. Cada épica está pensada para convertirse en muchas tareas de 1-ciclo.













### REGLAS DE GESTIÓN DE EPICS (OBLIGATORIO)
1. **Secuencialidad:** Los EPICs deben numerarse consecutivamente (01, 02.. 10, 11...). Prohibido saltar números (ej. "EPIC 100").
2. **Unicidad:** No puede haber dos EPICs con el mismo número. Si se inserta uno nuevo, se desplazan los siguientes.
3. **Correspondencia:** El número del EPIC en este Plan Maestro es la VERDAD. `task.md` y otros docs deben alinearse a este ID.

EPIC 01 — Reorganización de Repositorio ✅ BACKEND COMPLETADO / ✅ FRONTEND COMPLETADO / ✅ ORDEN CANÓNICO ACTUALIZADO (2026-02-14)

 Objetivo
Que el repo sea navegable y la IA no "rompa cosas" por desorden.

---

Arquitectura de Carpetas

**Reglas Generales (CANÓNICO 2026-02-14):**
- **Idioma:** Preferencia ESPAÑOL para carpetas funcionales (`integraciones`, `servicios`, `procesos`), salvo términos técnicos estándar (`api`, `core`, `utils`, `static`, `scripts`).
- **Nivel máximo:** Evitar anidación profunda (> 4 niveles) salvo frontend modular.
- **Separación fuerte:** Runtime de app en `code/app`; procesos de negocio batch en `code/procesos`; utilidades manuales en `code/scripts`; operación de servidor en `ops/`.
- **Raíz de `code` limpia:** Permitido solo directorios funcionales + `requirements.txt`. Prohibido `.py` sueltos.
- **Frontend modular:** Cada módulo mantiene nombres únicos y explícitos (`pmo.html`, `dashboard.html`, etc.).

**Árbol Oficial (vigente):**

```text
/srv/monstruo_dev/
├── code/
│   ├── app/                         # Backend FastAPI (runtime principal)
│   │   ├── api/
│   │   │   ├── .README.md
│   │   │   └── routers/             # Endpoints por módulo (admin, tks, crm, bodega, erp, pmo, zabbix, etc.)
│   │   ├── core/
│   │   │   ├── db.py, deps.py, security.py, middleware.py
│   │   │   ├── tickets_service.py, jobs_engine.py, notifications.py
│   │   │   └── ai/                  # Inicialización y bridge de IA
│   │   ├── domain/                  # Dominio puro (catálogo y reglas de negocio)
│   │   ├── integraciones/           # Adaptadores externos (Laudus, Parrotfy)
│   │   ├── jobs/                    # Tareas programadas ligadas al backend
│   │   ├── servicios/               # Servicios de negocio reutilizables
│   │   ├── utils/                   # Helpers internos y compatibilidad legacy
│   │   ├── workers/                 # Workers de soporte (ej: integrations_worker.py)
│   │   ├── workflows/               # Motor de workflow y persistencia asociada
│   │   ├── procesos/                # Proceso legado específico del backend
│   │   ├── main.py                  # Entrypoint (uvicorn app.main:app)
│   │   └── workflow_db_legacy.py
│   ├── static/                      # Frontend modular
│   │   ├── .README.md
│   │   ├── index.html
│   │   ├── manifest.json
│   │   ├── service-worker.js
│   │   └── modulos/
│   │       ├── _compartido/         # Base CSS/JS global
│   │       ├── login/
│   │       ├── dashboard/
│   │       ├── crm/
│   │       ├── configuracion/
│   │       ├── pmo/
│   │       ├── tks/                 # css/, js/, tks.html
│   │       ├── bodega/              # inventario/, catalogo/, pendientes/, analisis/, js/, css/
│   │       ├── erp/                 # resumen/, facturacion/, conciliacion/, cobranza/, ciclos/, bancos/, clientes/, prefactura/, css/, erp.html
│   │       ├── ultron/
│   │       └── zabbix/
│   ├── procesos/                    # Jobs batch de negocio (fuera del ciclo HTTP)
│   │   ├── integracion/
│   │   ├── mantenimiento/
│   │   └── ai/
│   ├── scripts/                     # Scripts manuales operativos (ordenados por propósito)
│   │   ├── README.md
│   │   ├── debug/
│   │   ├── migrations/
│   │   ├── maintenance/
│   │   └── seed/
│   ├── ops/                         # Artefactos operativos internos de code
│   │   ├── docker/
│   │   │   └── Dockerfile.api
│   │   └── herramientas/
│   │       └── dev/                 # verify_crm.py, verify_discrepancy.py
│   ├── tools/
│   │   └── ws-scrcpy/
│   └── requirements.txt
├── data/                            # Persistencia y archivos runtime de DEV
│   ├── tickets/                     # Adjuntos de ticketera (runtime)
│   │   └── <ticket_id>/
│   │       └── attachments/
│   │           └── <archivo_adjunto>
│   └── cartola_sintetica.csv        # Fixture de pruebas/validación local
├── docs/                            # Documentación oficial del proyecto
│   ├── .README.md
│   ├── PLAN_MAESTRO_MONSTRUO.md     # Guía maestra de construcción y prioridades
│   ├── PROYECTO_CONTEXTO.md         # Contexto operativo y estado del proyecto
│   ├── PROMPT_CHAT_UNIVERSAL.md     # Prompt base para agentes
│   ├── ESTANDARES.md                # Estándares de implementación
│   ├── estructura_repo.json
│   ├── apis/                        # Contratos de APIs externas
│   │   ├── laudus_openapi.json
│   │   └── parrotfy_openapi.yaml
│   ├── demo/                        # Material de demo y métricas
│   │   ├── escenarios.md
│   │   ├── guion_demo.md
│   │   └── kpis.md
│   ├── deploy/                      # Guías y plantillas de despliegue
│   │   ├── README.md
│   │   ├── nginx/
│   │   │   ├── erp.telconsulting.cl.md
│   │   │   └── login.telconsulting.cl.md
│   │   └── plantillas_env/
│   │       ├── README.md
│   │       ├── env.base.example
│   │       ├── env.local.example
│   │       ├── env.server.dev.example
│   │       └── env.server.example
│   ├── ia/                          # Políticas y prompts de IA
│   │   ├── politicas_central.json
│   │   └── prompts/
│   │       ├── admin_rules.txt
│   │       ├── auto_resolve_rules.txt
│   │       ├── categ_rules.txt
│   │       ├── duplicates_rules.txt
│   │       ├── global_context.txt
│   │       └── instructor_rules.txt
│   ├── playbooks/                   # Runbooks de incidentes/integraciones
│   │   ├── generic.md
│   │   ├── integration_parrotfy_payments_api_500.md
│   │   └── parrotfy_missing_invoice.md
│   ├── sql/
│   │   └── pmo_v1.sql.txt
│   └── windows/
│       ├── install_shortcut.ps1.txt
│       ├── monstruo_silent.vbs.txt
│       └── monstruo_start.bat.txt
├── ops/                             # Operación y mantenimiento del sistema
│   ├── .README.md
│   ├── compose/
│   │   └── docker-compose.yml.md
│   ├── control/                     # Scripts de control operativo local
│   │   ├── control_ia.sh
│   │   ├── control_monstruo.sh
│   │   ├── control_terreneitor.sh
│   │   └── limpiar_ram.sh
│   ├── entornos/
│   │   └── ejemplo.env
│   ├── guardian/                    # Monitoreo y vigilancia de integridad
│   │   ├── .README.md
│   │   ├── config/
│   │   │   └── configuracion_guardian.json
│   │   ├── estado_supervisor.json
│   │   ├── reportes/
│   │   │   └── reporte_nombres_prohibidos__2026-01-27__172848.json
│   │   └── scripts/
│   │       ├── enviar_a_ia_local.py
│   │       ├── install_hooks.sh
│   │       ├── orden_guardian.py
│   │       ├── saneador_nombres_prohibidos.py
│   │       ├── supervisor_eventos.py
│   │       ├── verify_auth.py
│   │       ├── vigilante_archivos.py
│   │       └── vigilante_registros.py
│   ├── herramientas/                # Utilidades de soporte técnico
│   │   ├── .README.md
│   │   ├── add_postgres_constraints.py
│   │   ├── migrate_categories_mirror.py
│   │   ├── migrate_sqlite_to_postgres.py
│   │   ├── ai/
│   │   │   ├── snapshot_for_training.py
│   │   │   ├── start_llm_server.sh
│   │   │   └── verify_ai_endpoints.py
│   │   ├── db/                      # Migraciones/fixes de base de datos
│   │   │   ├── categorize_laudus_data.py
│   │   │   ├── categorize_orphans.py
│   │   │   ├── db_migrate_catalogo_v2.py
│   │   │   ├── db_migrate_ticketera_catalogo.py
│   │   │   ├── db_migrate_tks_v2.py
│   │   │   ├── db_top_tables.py
│   │   │   ├── fix_bodega_hierarchy.py
│   │   │   ├── fix_postgres_catalogo.py
│   │   │   ├── migrate_hidden_categories.py
│   │   │   ├── seed_catalogo_base.py
│   │   │   └── sync_m2m_categories.py
│   │   ├── deploy/                  # Scripts de arranque/deploy/validación
│   │   │   ├── deploy.sh
│   │   │   ├── generate_universal_prompt.py
│   │   │   ├── iniciar_todo.sh
│   │   │   ├── start.sh
│   │   │   └── verify_structure.py
│   │   └── dev/                     # Debug y utilidades de desarrollo
│   │       ├── create_manual_user.py
│   │       ├── debug_bank_lines.py
│   │       ├── debug_db.py
│   │       ├── debug_invoice_service.py
│   │       ├── debug_invoices.py
│   │       ├── debug_matching.py
│   │       ├── debug_no_matches.py
│   │       ├── debug_sales.py
│   │       ├── debug_sync.py
│   │       ├── debug_taxonomy.py
│   │       ├── fix_schema_constraints.py
│   │       ├── format_contexto.py
│   │       ├── generate_fake_csv.py
│   │       ├── get_laudus_codes.py
│   │       ├── probe_laudus_journal.py
│   │       ├── probe_laudus_ledger.py
│   │       ├── proxy_vm.env.example
│   │       ├── proxy_vm_env.sh
│   │       ├── refine_history.py
│   │       ├── test_laudus_details.py
│   │       ├── test_pdf_logic.py
│   │       └── test_upload_parse.py
│   └── systemd/                     # Unidades de servicio legacy/infra
│       ├── .README.md
│       ├── api.service
│       ├── guardian-archivos.service
│       ├── guardian-envio.service
│       ├── guardian-envio.timer
│       ├── guardian-limpieza.service
│       ├── guardian-limpieza.timer
│       ├── guardian-registros.service
│       └── guardian-supervisor.service
├── tests/                           # Se detalla en fase siguiente
├── docker-compose.yaml
└── AGENTS.md
```

---

### Decisiones Específicas

| Decisión | Antes | Después | Razón |
|----------|-------|---------|-------|
| **Backend** | `code/backend` | `code/app` | Estándar FastAPI |
| **Integraciones** | `integrations` | `integraciones` | Consistencia español |
| **Procesos** | Mezclado con ops | `code/procesos` separado | Lógica negocio vs infraestructura |
| **Scripts manuales** | `.py` sueltos en `code/` y `code/scripts/` | `code/scripts/{debug,migrations,maintenance,seed}` | Menor riesgo operativo y mayor mantenibilidad |
| **Frontend** | Archivos sueltos por módulo | `static/modulos/` por contexto | Component-Based y cambios aislados |
| **Docker app** | `code/docker/` | `code/ops/docker/` | Agrupar artefactos operativos dentro de `code/ops` |
| **Raíz de `code`** | Scripts mezclados con runtime | Solo carpetas funcionales + `requirements.txt` | Navegación y auditoría rápida |
| **Auth** | Session opaca (DB) | **JWT Stateless** | Escalabilidad/Seguridad (EPIC 02) |

---

### Tareas Completadas (Backend)

- [x] Renombre masivo de carpetas (`app`, `procesos`, `herramientas`)
- [x] Limpieza de raíz `code/app` (Clean Architecture)
- [x] Reorganización `code/static` (Component-Based con `modulos/`)
- [x] Consolidación `data/` (backups rotativos, eliminado cache/import)
- [x] Limpieza `docs/` (12 archivos eliminados, estándares unificados)
- [x] Reorganización `ops/` (systemd, guardian, herramientas categorizados)
- [x] Limpieza raíz de `code` (sin `.py` sueltos; solo directorios funcionales + `requirements.txt`)
- [x] Implementación **Manifiestos Estrictos** (`.README.md` con allowlists)
- [x] Script de auditoría (`ops/herramientas/deploy/verify_structure.py`)
- [x] Renombre scripts a Español (`trabajador_asistente_ia.py`, etc.)
- [x] Estandarización de scripts operativos en `code/scripts/{debug,migrations,maintenance,seed}`
- [x] Eliminación de artefactos runtime versionados (`code/server.log`)

---

### 🆕 Tareas Frontend Modular (2026-02-01)

**Objetivo:** Separar cada pestaña/submódulo en archivos `.html`, `.css`, `.js` independientes para:
- ✅ Reducir "blast radius" de cambios
- ✅ Facilitar trabajo de IA (solo ve código relevante)
- ✅ Alinearse con separación del backend (ya correcta)
- ✅ Establecer estándar para futuras features

**Módulos a Refactorizar:**

- [x] **ERP** (Prioridad CRÍTICA) ✅ COMPLETADO 2026-02-01
  - [x] Extraer "Resumen" → `erp/resumen/`
  - [x] Extraer "Facturación" → `erp/facturacion/`
  - [x] Extraer "Conciliación" → `erp/conciliacion/`
  - [x] Extraer "Cobranza" → `erp/cobranza/`
  - [x] Crear router dinámico en `erp.html`
  - [x] Extraer CSS compartido → `css/erp-shared.css`

- [x] **Bodega** ✅ COMPLETADO (2026-02-01)
  - [x] Auditar estructura (4 tabs + 3 modales complejos + 5 archivos JS)
  - [x] Extraer "Inventario" → `bodega/inventario/`
  - [x] Extraer "Catálogo" → `bodega/catalogo/`
  - [x] Extraer "Pendientes" → `bodega/pendientes/`
  - [x] Extraer "Análisis" → `bodega/analisis/`
  - [x] Crear router dinámico en `bodega.html`
  - **Nota:** Mantener modales/drawers compartidos en el shell para evitar regresiones.
  
- [ ] **PMO** (Auditar primero)
  - [ ] Verificar si tiene sub-pestañas mezcladas

- [ ] **Dashboard** (Auditar primero)
  - [ ] Verificar si tiene sub-pestañas mezcladas

**Tiempo Estimado Restante:** 0 horas (Frontend modular completado)

**Nota:** El patrón está documentado en este Plan Maestro (sección "Árbol Oficial"). Aplicar igual estructura a todos los módulos.


---

### Criterio de Aceptación

✅ **Arranque OK** - Sistema inicia sin errores  
✅ **Endpoints base OK** - APIs responden correctamente  
✅ **UI carga OK** - Frontend accesible y funcional  
✅ **Estructura verificada** - `verify_structure.py` reporta OK  
✅ **Frontend modular** - Cada pestaña en carpeta propia (html+css+js)
✅ **Cambios aislados** - Modificar 1 pestaña no afecta otras
✅ **Code limpio** - No existen scripts `.py` sueltos en `code/`
✅ **Scripts ordenados** - Todo script manual está en `code/scripts/*` según tipo

### Verificación Rápida de Orden (operativo)

```bash
# Debe salir VACÍO (sin .py sueltos en code/)
find code -maxdepth 1 -type f -name '*.py'

# Debe listar solo categorías válidas bajo code/scripts
find code/scripts -maxdepth 2 -type f | sort
```
  

---





















---

EPIC 02 — Auth/RBAC + Sesiones [BACKEND COMPLETADO]
Tareas:
- [x] Modelo users/roles/permisos (`auth_service.py` + `config.py`)
- [x] JWT + refresh (Stateless via `security.py`)
- [x] Middleware RBAC por router (`deps.require_permission`)
- [x] Auditoría de login (`audit.log_audit` en DB)
- [ ] UI oculta menús sin permiso (Pendiente Frontend)

Aceptación:

acceso directo URL → 403

logs de auditoría correctos



















---

EPIC 03 — Auditoría y trazabilidad (core) [COMPLETADO]
Tareas:
- [x] audit_log estándar (Tabla DB + triggers)
- [x] decorador “audit_action” (Backend)
- [x] niveles de criticidad (Severity column)
- [x] export auditoría (csv/json endpoint)

Aceptación:

cualquier operación crítica genera audit entry











---

EPIC 04 — Motor de Jobs / Integraciones [COMPLETADO]

Tareas:
- [x] tabla sys_jobs (job_execution_log no se usa en v1)
- [x] scheduler (BackgroundTasks + Polling Loop)
- [x] retry + DLQ (exponencial backoff)
- [x] pantalla “Integraciones” (API /api/jobs/dashboard)

Aceptación:
- [x] pipeline corre y deja trazabilidad











---

EPIC 05 — ERP Ventas (Factura/NC/ND) [COMPLETADO]

Tareas:

- [x] CRUD facturas (Tabla `invoices` + `invoice_items`)
- [x] estados (Draft -> Issued -> Paid/Void strict lifecycle)
- [x] NC/ND referenciadas (Void genera NC automática)
- [x] Integración Bodega (Rebaja de stock al emitir / Devuelve al anular)
- [x] Integración Laudus (Espejo: Proxy PDF + Payments)
- [ ] export DTE (Nativo)

Aceptación:
- [x] “anulación” se modela como NC/ND, no delete









---

EPIC 06 — CRM / Clientes (Espejo Laudus) [COMPLETADO]
 
 Tareas:
- [x] registro clientes (Tabla `customers` con RUT, Giro, etc.)
- [x] sincronización Laudus (Job `SYNC_CUSTOMERS`)
- [x] API CRM (Búsqueda local rápida)
- [x] interacciones (timeline + creación de notas)
- [x] validación de cliente en interacciones
- [x] upsert por external_id o RUT en sync
 
 Aceptación:
- [x] clientes unificados y disponibles offline (cache)

recordatorios

tickets automáticos por mora

Aceptación:

cobranza visible y auditable






---

EPIC 07 — Conciliación bancaria ✅ COMPLETADO (2026-02-01)

**Estado:** Infraestructura completa y probada. Esperando cartolas CSV reales del banco para uso en producción.

Tareas:

- [x] Schema DB (4 tablas: `bank_accounts`, `bank_statements`, `bank_statement_lines`, `bank_reconciliations`)
- [x] Sincronización Cuentas Bancarias (Desde Laudus `/accounting/accounts`)
- [x] Sincronización Movimientos Laudus (`/accounting/ledger` - Funcional)
- [x] Parser CSV Multi-Banco (Santander, BCI con validación de formato)
- [x] Motor de Matching Automático (Exacto 100% + Fuzzy 80%)
- [x] API Router `/api/conciliacion` (7 endpoints: banks, upload, sync, movements, statements, match, matches)
- [x] UI Profesional (Tab Conciliación en ERP, estilo alineado a Facturación)
- [x] Testing con CSV Sintético (4 matches detectados exitosamente)

Aceptación:
- ✅ Conciliación no duplica movimientos (verificado por `statement_id` + línea única)
- ✅ Auditoría implementada (created_at, created_by en reconciliations)
- ✅ UI consistente con módulo Facturación (mismo estilo visual)
- ✅ Matching funcional (exacto por doc+amount, fuzzy por amount+fecha±3días)

**LIMITACIÓN ACTUAL:**  
Sistema funcional pero requiere **cartolas CSV reales del banco** para producción.  
Probado exitosamente con CSV sintético generado a partir de datos de Laudus.

**Archivos Clave:**
- Backend: `code/app/api/routers/conciliacion.py`, `code/app/servicios/bank_parser.py`, `code/app/servicios/bank_matcher.py`
- Frontend: `code/static/modulos/erp/erp.html` (líneas 264-319), `code/static/modulos/erp/js/bancos.js`
- Sync: `ops/herramientas/integraciones/sync_bancos_laudus.py`
- Testing: `ops/herramientas/dev/generate_fake_csv.py`










---

EPIC 08 — Admin Dashboard (Consola Operativa) [COMPLETADO]
 
 Tareas:
- [x] Backend Ops (Aggregator API `/api/ops/dashboard`)
- [x] Frontend UI (HTML/JS con auto-refresh)
- [x] Integración KPIs (Tickets, Ventas, Jobs)
- [x] Queries alineadas a esquema real (estado/severidad/sys_jobs)
 
 Aceptación:
- [x] Vistazo único de salud del sistema








---

EPIC 09 — Bodega + Catálogo [COMPLETADO]

Tareas:
- [x] catálogo canónico (Tabla `products` + Sync Parrotfy)
- [x] stock real (Columna `stock_current` + Kardex)
- [x] movimientos (Tabla `inventory_movements` + Tipos SALE/RETURN/ADJUST)
- [x] API Bodega (CRUD Productos + Kardex View)
- [x] multi-categoría catálogo (Tabla `cat_item_categories` + API)
- [x] filtro de categoría incluye subcategorías (vista Catálogo)
- [x] sync de stock Laudus en entrada a Bodega (apply_stock)
- [x] UI: Kardex en drawer derecho
- [x] UI: búsqueda inventario case-insensitive (cliente)
- [x] UI: normalización visual en minúsculas (nombres/categorías)
- [x] base de categorías consolidada (EQUIPOS/MATERIALES)
- [ ] Ubicaciones (Pendiente v2)
- [x] UI: Búsqueda rápida y vista de inventario funcional
- [ ] Windows Launcher (Script .vbs/bat para inicio silencioso)

Aceptación:
- [x] stock consistente
- [x] catálogo navegable con categorías y subcategorías

### Nota de Arquitectura: Orden y Jerarquía del Catálogo
**1. Ramas Principales:**
El árbol de categorías se ha consolidado estrictamente en dos ramas madre (provenientes de Laudus). Todo item debe vivir aquí:
*   **EQUIPOS (ID 110):** Hardware activo, dispositivos, computadores.
*   **MATERIALES (ID 106):** Insumos, cables, ferretería.

**2. Lógica "Sin Asignar" (Oculta):**
*   Existe una subcategoría especial llamada `Sin Asignar` dentro de cada rama madre (ej: `EQUIPOS > Sin Asignar`).
*   **Propósito:** Contener items que pertenecen a la rama pero no tienen una subcategoría específica (ej: un equipo suelto que no es ni router ni pc).
*   **Visibilidad:** Esta carpeta tiene `is_hidden=1` en base de datos. La API la oculta por defecto y solo la muestra si se pide `?include_hidden=true`.
*   **Sync:** Un script (`sync_m2m_categories.py`) asegura que la tabla intermedia de categorías (`cat_item_categories`) refleje esta realidad.

**4. Estructura de Categorías (Taxonomía Estricta):**

Para evitar desorden, se define una estructura jerárquica obligatoria de 3 niveles.

*   **NIVEL 1: CONTEXTO / ESTADO OPERATIVO (Tipos de Bodega)**
    *   **BODEGA:** Stock disponible, central, en estantería.
    *   **ARRIENDO:** Stock en poder de clientes (servicio activo), comodatos.
    *   **BAJAS:** Stock dañado, obsoleto, robado o en proceso de destrucción.

*   **NIVEL 2: CLASE DEL ÍTEM (Tipos de Cosas)**
    *   **EQUIPOS:** Activos fijos, serializados (Notebooks, Routers, Celulares).
    *   **HERRAMIENTAS:** Instrumentos de trabajo (Taladros, Fusionadoras, Alicates).
    *   **MATERIALES:** Consumibles, no serializados (Cables, Conectores, Tornillos, Cemento).

*   **NIVEL 3: SUBCATEGORÍAS ESPECÍFICAS**
    *   *Ejemplos (Equipos):* Computadores, Celulares, Routers, Switches.
    *   *Ejemplos (Herramientas):* Manuales, Eléctricas, Inalámbricas, Medición.
    *   *Ejemplos (Materiales):* Madera, Fierro, Pernos, Cables, Ferretería.

*   **NIVEL 4 (OPCIONAL): DETALLE / MARCA / COMPONENTES**
    *   *Uso:* Refinar marcas específicas o accesorios vinculados.
    *   *Ejemplos (Celulares):* Samsung, iPhone, Cargadores, Audífonos.
    *   *Ejemplos (Cables):* 15mts, 30mts, Bobinas.

**5. Sincronización de Espejo (Mirroring):**
*   Las ramas de `BODEGA`, `ARRIENDO` y `BAJAS` deben ser idénticas estructuralmente en los Niveles 2, 3 y 4.
*   **Regla de Oro:** Si se crea una categoría en una rama (ej: `BODEGA > EQUIPOS > Nuevos`), el sistema debe crearla automáticamente en las otras dos (`ARRIENDO` y `BAJAS`), manteniendo la consistencia de IDs y nombres.

> [!WARNING]
> **Estado Actual (2026-01-30):** La lógica de backend (Mirroring) y la estructura de BD están implementadas y limpias. Sin embargo, la visualización en el Frontend (árbol JS) ha presentado problemas de "items huérfanos" apareciendo erróneamente en la raíz. Se dejó un parche (`hide orphans`) pero falta depuración fina de UX. Tarea pausada.

*Nota: Mover un ítem de "Bodega" a "Arriendo" implicará un movimiento en el Nivel 1 del árbol (cambio de categoría raíz), reflejando su cambio de estado lógico.*
*   Se eliminaron ramas antiguas (IDs 14 y 19) que duplicaban nombres. Si ves IDs 110/106, son los correctos.

---

EPIC 10 — IA Bodega (dedupe/categoría)

Tareas:

*   [x] **Soporte de Imágenes:**
    *   Backend: Columna `image_url` en `cat_items` (DB ID 7).
    *   Frontend: Visualización de miniaturas y comparación visual A/B.
*   [x] **Resolución de Duplicados en UI:**
    *   Modal de interacción con opción "Merge" (Conservar A/B) y "Ignorar".
    *   Detección y manejo de **Variantes** (mismo producto, distinta característica) con flujo de reclasificación masiva.
*   [x] **Selector de Categorías (Wizard):**
    *   Componente jerárquico con búsqueda integrada.
    *   Creación de categorías "inline" (al vuelo) durante la clasificación.
*   [ ] ** IA Siguiente Nivel:**
    *   Embeddings/similitud (local) para sugerencias más difusas.
    *   Entrenamiento con feedback recolectado (`ia_bodega_casos`).

Aceptación:

IA no ejecuta masivo sin revisión humana (cumplido: flujo `resolver_duplicado` requiere acción explícita).








---

EPIC 11 — Ticke-Tera (Ticketera) [PRIORIDAD MÁXIMA - REEMPLAZO MESA EXTERNA]

Objetivo de negocio:
- Reemplazar la mesa externa contratada por la empresa con una mesa interna de estándar productivo profesional.
- Criterio de avance: no basta "funciona en dev"; debe quedar apta para operación diaria real sin regresiones de flujo.

Tareas:
- [x] CRUD ticket (API `/api/tks/tickets` + RBAC)
- [x] Estados y SLA (cálculo por severidad + notificaciones in-app)
- [x] Comentarios y timeline base por eventos (`ticket_comments`)
- [x] UI Ticketera V3: Resumen (KPIs + Pivot), Lista, Kanban y detalle
- [x] Responder por correo desde detalle (`POST /api/tks/tickets/{ticket_id}/reply-email`)
- [x] Mantención de hilo de correo (`In-Reply-To` / `References` + `email_thread_id`)
- [x] Anti-duplicado de correos salientes (`outgoing_pending` + dedupe por ventana corta)
- [x] Parser de correo entrante por hilo y asunto (actual + formatos legacy)
- [x] Formato de código actualizado a `TK-DD-MM-YYYY-NNNN`
- [x] Hardening create_ticket (fail-safe en auto-asignación/notificaciones + validación de ID post-INSERT)
- [x] Fix de fluidez UI (AbortController + cancelación de requests + cache TTL)
- [ ] Adjuntos en respuesta por correo (UI + backend real sobre `attachments_json`)
- [ ] Historial de correos completo en detalle (entrada/salida con payload legible)
- [ ] Worker real para escalamiento WhatsApp/3CX (hoy se agenda en DB, falta ejecutor de canal)
- [ ] Auto-respuesta configurable de recepción de correo (actualmente desactivada)
- [ ] Suite de tests E2E ticketera (`create -> reply -> dedupe -> incoming thread match`)
- [ ] Checklist técnico anti-cruce DEV/PROD para Ticketera (SMTP, base URL, credenciales y jobs)

Aceptación:
- [x] Crear ticket no cae en 500 por fallas no críticas de auto-asignación/notificaciones
- [x] Respuesta por correo se envía desde el detalle y registra evento en timeline
- [x] Reintento/doble envío en ventana corta no duplica correo saliente
- [x] Código de ticket usa formato `TK-DD-MM-YYYY-NNNN` en creación nueva
- [ ] Adjuntar archivos en respuesta por correo operativo de punta a punta
- [ ] Validación automatizada de separación DEV/PROD para flujo de correo y jobs
- [ ] EPIC 11 certificado para reemplazo de mesa externa (Go/No-Go profesional firmado)


---

EPIC 12 — Módulo Jefe de Proyectos (PMO) [ESTADO: IMPLEMENTADO FASE 1]

**Concepto Central:** Hub operativo técnico ("Cockpit"). No es ventas (CRM) ni admin (ERP).
**Responsable:** JP + IA

Tareas:
- [x] **Diseño de Modelo de Datos:** Schema SQL (`pmo_proyectos`, `pmo_costos`, `pmo_bitacora`).
- [x] **Backend:** Router `/api/pmo`, CRUD Proyectos, Bitácora IA.
- [x] **Frontend:** Dashboard operativo, Cards V3, Acordeón detalle, Estados.
- [x] **IA Router:** Ingesta de bitácora (texto/correo) y clasificación inicial.
- [ ] **Workflow Estricto:** Gates que bloquean avance si falta info.
- [ ] **Gestión de Recursos:** Asignación de cuadrillas y vehículos.

Aceptación:
- [x] Rentabilidad y avance visibles (Dashboard V3).
- [ ] IA deriva correos a bodega/finanzas automáticamente.


---

EPIC 13 — Jira sync (Anteriormente 12)

Tareas:
- create issue
- sync status
- sync comments
- mapping

Aceptación:
- 2-way mínimo viable


---

EPIC 14 — Zabbix → Ticket (Anteriormente 13)

Tareas:
- webhook receiver
- dedupe y agregación
- incidente mayor
- notificaciones

Aceptación:
- alerta alta crea ticket/incidente


---

EPIC 15 — Preventa configurador + proveedores

Tareas:
- plantillas
- formularios dinámicos
- motor reglas de alcance
- scoring proveedores
- comparador

Aceptación:
- propuesta consistente con alcance


---

EPIC 16 — Reporting

Tareas:
- dashboards gerencia
- export
- reportes cliente
- snapshots mensuales

Aceptación:
- reportes reproducibles y auditables


---

EPIC 17 — IA central ULTRON (gobernanza + políticas)

Tareas:
- registry de políticas
- “colisión” entre agentes
- logging prompts
- escalamiento (ticket/alerta)

Aceptación:
- IA no rompe políticas; si hay choque, alerta y bloquea


---

EPIC 18 — Housekeeping & Fixes (Discrepancias) [COMPLETADO]

Tareas:
- [x] Migrar Stock Sync a Laudus (Source of Truth)
- [x] Lógica de Discrepancias (No auto-ajuste)
- [x] Creación automática de Tickets (Severidad Alta)

Aceptación:
- [x] Stock fantasma genera alerta en lugar de ajuste silencioso


---

EPIC 19 — Cobranza Avanzada & Automatización [FASES 1-2 COMPLETADAS]

Tareas:
- [x] **Fase 1: Dashboard de Deuda (Aging)**
    - [x] Endpoint `/api/collection/debtors` (Reglas de negocio 30/60/90 días)
    - [x] UI Semáforo de Riesgo (Critical/Warning/Normal)
    - [x] Sincronización de Facturas Laudus (Issuer ID)

- [x] **Fase 2: Gestión y Bitácora**
    - [x] Modelo de datos `collection_actions` (historial persistente)
    - [x] Modal de Gestión (Registro de llamadas, correos, notas)
    - [x] Fix: Normalización de nombres de cliente (Title Case)

- [-] **Fase 3: Automatización de Correo (En Progreso)**
    - [x] Infraestructura SMTP (`app.core.email.py`)
    - [x] Configuración Dinámica (Tabla `system_settings` + UI en Resumen)
    - [x] Wiring: Botón "Generar Borrador" crea contenido inteligente
    - [x] Wiring: Botón "Guardar" envía email real (si action_type='EMAIL')
    - [ ] Tracking de Apertura (Pixel 1x1)
    - [ ] Scheduler Robot (Envío automático sin intervención)

Aceptación:
- [x] Deuda crítica (>60 días) se visualiza en rojo
- [x] Gestión guarda historial y envía correo si corresponde
- [ ] Robot envía correos solo en horario hábil y respeta feriados

---

EPIC 20 — Centralización Bancaria (Terminal Unificado) ✅ COMPLETADO (2026-02-05)

**Estado:** Módulo operativo dentro del ERP. Permite el control remoto de dispositivos móviles (Android) para acceso a cuentas fintech (MACH, MercadoPago, etc.) con gestión de exclusividad.

Tareas:
- [x] Contenedor Docker para `ws-scrcpy` (platform-tools v36)
- [x] Conexión ADB estable vía Wireless Pairing (IP:Puerto dinámica)
- [x] Módulo "Bancos" en Frontend (Iframe con streaming en vivo)
- [x] Sistema de bloqueo de sesión (Acquire/Release/Heartbeat)
- [x] Backend Router `/api/bancos` con autenticación híbrida (Cookies/Headers)
- [x] Limpieza de UI (Eliminación de controles físicos e instalador manual)

Aceptación:
- [x] Streaming fluido del celular dentro de la pestaña ERP > Bancos
- [x] Control exclusivo: Solo un usuario puede operar el terminal a la vez
- [x] Liberación automática de sesión tras 10 minutos de inactividad
- [x] Seguridad: Acceso restringido por rol y sesión válida


---

EPIC 21 — Motor de Reglas de Facturación [PENDIENTE]

**Objetivo:** Soportar ciclos de facturación personalizados por cliente (Mensual, Bimensual, Trimestral, Anual) para automatizar la generación de borradores y alertas.

Tareas:
- [x] Modelado de datos: Tabla `billing_rules` vinculada a `customers`
- [x] Desarrollo de Job Diario: Evaluador de `last_invoice_date` + `frequency`
- [ ] Sistema de Alertas: Notificar a Finanzas "Por Facturar" 
- [x] Generación automática de Borradores de Factura (Drafts) en ERP
- [x] UI de Configuración de Reglas por Cliente (con integración CRM)

Aceptación:
- [ ] El sistema genera una alerta o borrador exacto según la fecha de ciclo
- [ ] Permite excepciones manuales (posponer o saltar periodos)

---

EPIC 22 — Flujo Proyecto a Caja (Project-to-Cash) [PENDIENTE]

**Objetivo:** Vincular el avance de Proyectos (PMO) con la Facturación, alertando a Finanzas cuando se cumplen hitos facturables.

Tareas:
- [ ] Integración entre módulos: PMO -> Finanzas (Trigger por Hito Completado)
- [ ] Dashboard Finanzas: Widget "Proyectos listos para facturar"
- [ ] Flujo de Validación: JP marca hito -> Finanzas aprueba y emite DTE
- [ ] Trazabilidad de Ingresos: Link directo entre Factura y Hito de Proyecto

Aceptación:
- [ ] Finanzas tiene visibilidad proactiva de hitos completados sin intervención manual
- [ ] Cada factura emitida tiene rastro del hito técnico que la originó

---

EPIC 23 — Sincronización Comercial Unificada [PENDIENTE]

**Objetivo:** Evitar desajustes de información entre Área Comercial (CRM) y Operaciones/Finanzas asegurando un "Single Source of Truth".

Tareas:
- [ ] Definir Ficha Maestra del Cliente en CRM (Campos mandatorios para Facturación)
- [ ] Propagation Job: Sincronización CRM -> Laudus / Parrotfy / Ticketera
- [ ] Auditoría de cambios en datos críticos (Razón Social, RUT, Dirección de Facturación)
- [ ] Interfaz de validación de discrepancias de contacto comercial vs facturación

Aceptación:
- [ ] Los cambios en el CRM se propagan automáticamente a los sistemas satélites en < 5 min
- [ ] El flujo de facturación no se bloquea por falta de datos mandatarios (validados en CRM)

---

## Bitácora Operativa — 2026-02-09 (DEV/PROD en paralelo sin abrir puertos)

### Contexto
- Restricción de red: firewall solo permite `80/443`.
- Decisión: mantener un único entrypoint HTTPS y enrutar a `prod` o `dev` por cookie.

### Arquitectura activa
- `PROD`:
  - rama: `main`
  - backend: `127.0.0.1:9000`
  - compose project: `monstruo`
- `DEV`:
  - rama: `dev`
  - backend: `127.0.0.1:9001`
  - compose project: `monstruo_dev`

### Selector de entorno (Nginx en proxy)
- URL para activar DEV:
  - `https://login.telconsulting.cl/__env/dev`
- URL para volver a PROD:
  - `https://login.telconsulting.cl/__env/prod`
- Cookie usada:
  - `monstruo_env=dev` (dominio `.telconsulting.cl`)
- Header de diagnóstico:
  - `X-Monstruo-Env: dev|prod`

### Verificación de versión desplegada
- PROD:
  - `https://login.telconsulting.cl/version` -> `branch = main`
- DEV (con cookie dev activa):
  - `https://login.telconsulting.cl/version` -> `branch = dev`

### CI/CD actualizado
- Workflow `deploy.yml` ahora despliega por rama:
  - push a `main` -> deploy entorno productivo (`.env.server`)
  - push a `dev` -> deploy entorno dev (`.env.server.dev`)
- Script de deploy soporta:
  - `DEPLOY_COMPOSE_PROJECT`
  - `DEPLOY_STACK_NAME`
  - `HEALTH_URL` por entorno

### Archivos clave agregados/ajustados
- `.github/workflows/deploy.yml` (deploy por rama)
- `ops/herramientas/deploy/deploy.sh` (parametrización por stack)
- `docker-compose.yaml` (`container_name` dinámico por `STACK_NAME`)
- `docs/deploy/plantillas_env/env.server.dev.example` (plantilla para staging interno)
- `docs/deploy/README.md` (operación de entornos paralelo)

### Operación diaria recomendada
1. Desarrollar y push en `dev`.
2. Activar entorno DEV con `/__env/dev`.
3. Validar cambios funcionales en dominios reales.
4. Si aprueba: PR `dev -> main`, merge manual.
5. Volver a PROD con `/__env/prod`.

### Nota importante de autenticación
- La base de `dev` puede partir sin usuarios.
- Se sincronizaron usuarios de `prod` a `dev` el 2026-02-09 para igualar credenciales.
- Si vuelve a pasar “credenciales inválidas” en DEV, revisar tabla `users` del stack `monstruo-dev`.
