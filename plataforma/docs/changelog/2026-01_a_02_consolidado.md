# Changelog consolidado 2026-01 a 2026-02 (bitácora histórica por módulo)

Esta es la bitácora consolidada del arranque del proyecto, organizada por módulo (no estrictamente cronológico). Cubre las primeras semanas del proyecto.

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

### 2026-02-16 20:40 - EPIC 11 Ticketera: Ajuste anti-scroll modulo completo
- Solicitud: eliminar scroll interno en ventanas, hacer que los paneles crezcan con el contenido y usar min/max de altura con scroll controlado solo al exceder el maximo.
- Entregable:
  - `code/static/modulos/tks/css/tks.css`: alturas base del modulo con variables (`--tks-module-min-height`, `--tks-module-max-height`), aumento de altura util en `Lista/Detalle`, eliminacion de overflows internos en paneles y bloqueo de overflow horizontal.
  - `code/static/modulos/tks/css/tks.css`: normalizacion de tablas (`table-layout: fixed` + wrap) para evitar scroll horizontal.
  - `code/static/modulos/tks/css/tks.css`: estilo dedicado para resultados de vinculacion de clientes (`.tks-assoc-results`) con crecimiento natural y scroll solo al superar maximo.
  - `code/static/modulos/tks/js/tks_ui.js` y `code/static/modulos/tks/js/tks_main.js`: limpieza de estilos inline de resultados de clientes para respetar el layout responsive definido por CSS.
  - `code/static/modulos/tks/tks.html`: bump de versiones de assets (`tks.css`, `tks_ui.js`, `tks_main.js`) para invalidar cache.
- Verificacion:
  - Revisados los `overflow:auto` restantes para que queden solo en contenedores controlados (modulo principal y listas largas puntuales).
  - Confirmado bloqueo de overflow horizontal en vistas principales.
- Estado: CERRADO.

### 2026-02-16 20:46 - EPIC 11 Ticketera: aumento de maximo de altura + fix solapamiento en Lista
- Solicitud: aumentar significativamente la altura maxima util del modulo y corregir solapamiento de informacion en la pestaña Lista.
- Entregable:
  - `code/static/modulos/tks/css/tks.css`:
    - `--tks-module-max-height` subido a `calc(100vh - 24px)` (desktop).
    - en mobile (`@media <=900px`) `max-height` del contenedor ajustado a `calc(100vh - 24px)`.
    - tabla de Lista cambiada de `table-layout: fixed` a `table-layout: auto`.
    - encabezados de tabla dejaron de ser sticky (`position: static`) para evitar solape visual.
    - `.td-min` pasa a `white-space: normal` y `width: auto` para prevenir cruces en celdas.
  - `code/static/modulos/tks/tks.html`: cache-bust CSS a `tks.css?v=12`.
- Verificacion:
  - revisión directa de reglas CSS aplicadas y paths actualizados.
- Estado: CERRADO.

### 2026-02-16 20:49 - EPIC 11 Ticketera: maximo global manual ampliado (Lista/Operación)
- Solicitud: ampliar mucho el maximo de altura util y dejar claro donde ajustar manualmente para evitar scroll interno percibido en Lista y Operación.
- Entregable:
  - `code/static/modulos/tks/css/tks.css`:
    - `--tks-module-max-height` elevado a `2600px`.
    - `--tks-module-min-height` elevado a `clamp(720px, 78vh, 980px)` para evitar paneles visualmente pequeños.
    - comentario en `:root` indicando que esa variable es el punto de ajuste manual del maximo global.
    - override responsive (`@media <=900px`) actualizado para usar las mismas variables globales (sin reducir max/min en mobile).
  - `code/static/modulos/tks/tks.html`: cache-bust CSS a `tks.css?v=13`.
- Verificacion:
  - revisión de reglas aplicadas en `:root` y media query de `tks-container`.
- Estado: CERRADO.

### 2026-02-16 21:05 - EPIC 11 Ticketera: cards de gestión movidos arriba + timeline a ancho completo
- Solicitud: mover los cuadros laterales (estado/adjuntos/cliente) debajo del título y por encima del contenido de correo, para que la línea de tiempo use todo el ancho posible.
- Entregable:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - `renderDetail()` reestructurado: se elimina `aside` lateral y se agrega franja superior `tks-detail-top-cards` con los 3 cards.
    - feed/timeline y composer quedan en una sola columna principal de ancho completo.
  - `code/static/modulos/tks/css/tks.css`:
    - `tks-detail-layout` pasa a una sola columna.
    - nuevas clases `tks-detail-top-cards` y `tks-top-card` para distribución superior responsive.
    - ajuste de `tks-detail-main-col` para usar todo el ancho.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust: `tks.css?v=14`, `tks_ui.js?v=18`.
- Verificación:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
- Estado: CERRADO.

### 2026-02-16 21:08 - EPIC 11 Ticketera: rediseño de card Estado y gestión
- Solicitud: ajustar visual y estructura de `Estado y gestión` para un formato más claro/profesional.
- Entregable:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - nuevo bloque `tks-status-summary` con estado actual + metadatos rápidos (asignado y SLA).
    - editor de cambio de estado rediseñado (`tks-status-editor`) con selector + botón `Aplicar` en layout explícito.
    - hint contextual bajo editor y separación visual de `Acciones` administrativas.
  - `code/static/modulos/tks/css/tks.css`:
    - estilos nuevos para `tks-status-summary`, `tks-status-editor`, `tks-status-actions-wrap` y versión responsive del editor.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust assets: `tks.css?v=15`, `tks_ui.js?v=19`.
- Verificación:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
- Estado: CERRADO.

### 2026-02-16 21:13 - EPIC 11 Ticketera: card Cliente sin duplicados + botón asociar si desconocido
- Solicitud: evitar repetición de datos entre `Estado y gestión` y `Cliente`; en `Cliente` mostrar solo datos del cliente y botón de asociación cuando esté desconocido.
- Entregable:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - card `Cliente` reducido a: `Nombre`, `Email`, `ID Cliente`.
    - eliminación de campos no cliente (código, asignado, SLA, categoría, severidad) de ese card.
    - condición `Desconocido` + email origen para mostrar botón `Asociar correo a cliente` que abre `TksMain.openAssociateClientModal(...)`.
    - escape de comillas simples en email para onclick seguro.
  - `code/static/modulos/tks/css/tks.css`:
    - nuevo estilo `.tks-customer-link` para el bloque del botón de asociación.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust: `tks.css?v=16`, `tks_ui.js?v=20`.
- Verificación:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
- Estado: CERRADO.

### 2026-02-16 21:18 - EPIC 11 Ticketera: estado y gestión sin selector (acciones directas)
- Solicitud: mejorar el bloque `Estado y gestión`; el selector para cambiar de estado no convencía.
- Entregable:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - reemplazo del `select` por botonera de transiciones directas (`Cambiar a ...`).
    - cada acción llama directo a `TksMain.changeStatus(ticketId, estado)`.
    - fallback visual cuando no hay transiciones disponibles.
  - `code/static/modulos/tks/css/tks.css`:
    - nuevas clases `tks-status-quick-grid` y `tks-status-quick-btn`.
    - estilos por estado (`abierto`, `en_progreso`, `resuelto`, `cerrado`) para lectura rápida.
    - ajuste responsive para apilar acciones en mobile.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust: `tks.css?v=17`, `tks_ui.js?v=21`.
- Verificación:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
- Estado: CERRADO.

### 2026-02-16 21:19 - EPIC 11 Ticketera: remover botón Reasignar en Estado y gestión
- Solicitud: eliminar el botón `Reasignar` del bloque `Estado y gestión` en el detalle.
- Entregable:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - se elimina la construcción/render del botón `Reasignar` en `managementActions`.
    - limpieza de variable no usada (`canReassign`) en `renderDetail`.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust de UI a `tks_ui.js?v=22`.
- Verificación:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - búsqueda de texto `Reasignar` en `tks_ui.js`/`tks_main.js`: sin coincidencias de render en detalle.
- Estado: CERRADO.

### 2026-02-16 21:25 - EPIC 11 Ticketera: estado actual grande + subestados operativos en Estado y gestión
- Solicitud: quitar el “cuadro dentro de cuadro” en `Estado actual`, mostrar estado en grande con color por estado y habilitar gestión de subestados.
- Entregable:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - nuevo formato visual `listy` para `Estado actual` (texto grande, color semántico por estado y subestado visible).
    - agregado helper `subestadoLabel(...)` para nombres legibles de subestados.
    - bloque `Estado y gestión` ahora muestra `Subestado actual` y botones de transición por `allowed_next` del workflow.
    - botones de transición de subestado llaman `TksMain.transitionSubestado(ticketId, toSubestado)`.
  - `code/static/modulos/tks/js/tks_main.js`:
    - `openDetail()` ahora consulta también `/tickets/{id}/workflow` y pasa datos de workflow al render.
    - nueva acción `transitionSubestado(...)` conectada a endpoint de transiciones, con refresh de lista/detalle y toasts.
  - `code/static/modulos/tks/js/tks_api.js`:
    - nuevo método `transitionTicket(ticketId, body)` para `POST /api/tks/tickets/{ticket_id}/transitions`.
  - `code/static/modulos/tks/css/tks.css`:
    - estilo nuevo para `Estado actual` grande (`tks-status-display` + tonos por estado).
    - estilo para subestado visible (`tks-substatus-display`, `tks-subestado-current-chip`) y botones de transición de subestado.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust assets: `tks.css?v=18`, `tks_api.js?v=10`, `tks_ui.js?v=23`, `tks_main.js?v=23`.
- Verificación:
  - `node --check` PASS en `tks_api.js`, `tks_ui.js`, `tks_main.js`.
- Estado: CERRADO.

### 2026-02-16 21:27 - EPIC 11 Ticketera: extensión de subestados operativos (compra/tercero)
- Solicitud: permitir subestados más operativos en `Estado y gestión` (ejemplos: pendiente compra / pendiente cliente / pendiente terceros).
- Entregable:
  - `code/app/core/tickets_service.py`:
    - `SUBESTADOS_VALIDOS` extendido con `pendiente_compra` y `pendiente_tercero` (manteniendo `pendiente_cliente`).
    - `WORKFLOW_RULES` actualizado para exponer transiciones de espera operativa en tipos `incidencia`, `requerimiento` y `cambio`.
  - `code/static/modulos/tks/js/tks_ui.js`:
    - `subestadoLabel(...)` actualizado con etiquetas legibles para nuevos subestados.
- Verificación:
  - parseo sintáctico backend con `ast.parse` PASS (`tickets_service.py`).
- Estado: CERRADO.

### 2026-02-18 19:20 - EPIC 11 Ticketera: cierre Go/No-Go DEV (workflow legacy + ownership duro + E2E verde)
- Solicitud: cerrar validación profesional Go/No-Go en DEV y corregir bloqueos E2E detectados.
- Entregable:
  - `code/app/core/tickets_service.py`:
    - compatibilidad de transición legacy para `triage` en `transition_ticket` (`recibido -> asignado`; no-op si ya está asignado/avanzado).
    - workflow actualizado para reapertura formal: `resuelto/cerrado -> reabierto` en `incidencia`, `requerimiento`, `cambio`.
    - compatibilidad legacy adicional:
      - `requerimiento`: `asignado -> en_analisis`.
      - `requerimiento/cambio`: `en_validacion -> cerrado` (cierre directo legacy).
    - endurecimiento ownership: `add_comment` vuelve a exigir `_ensure_can_participate_ticket` para todos (admin sin rol técnico no comenta).
  - `tests/e2e_ticketera.py`:
    - flujo de reply adaptado a ownership profesional: autoasigna ticket al actor de prueba antes de `reply-email`.
  - `tests/e2e_api_full.py`:
    - smoke adaptado a ownership profesional: toma ticket (`asignado_a=args.user`) antes de agregar evento.
- Verificación:
  - `python3 tests/verify_hardening.py --check-api` PASS.
  - `python3 tests/e2e_api_full.py` PASS.
  - `python3 tests/e2e_ticketera.py` PASS.
  - parseo sintáctico por `compile(..., 'exec')` en:
    - `code/app/core/tickets_service.py` PASS.
    - `tests/e2e_ticketera.py` PASS.
    - `tests/e2e_api_full.py` PASS.
- Estado: CERRADO.

### 2026-02-19 11:36 - EPIC 11 Ticketera: refactor profundo seguro (fuente única de roles/workflow + hardening frontend + regresión en CI)
- Solicitud: implementar plan de refactor profundo manteniendo compatibilidad 100% y sin romper la app.
- Entregable:
  - Arquitectura interna (backend):
    - nuevo paquete interno `code/app/core/tickets/` para desacoplar políticas críticas sin romper la fachada pública:
      - `code/app/core/tickets/roles.py`: política centralizada de roles (gestión, ejecución técnica, despacho), validaciones `can_*`/`require_*`.
      - `code/app/core/tickets/workflow.py`: normalización de tipo/subestado, reglas de transición y compatibilidad legacy (`triage`, reapertura/cierre legacy).
      - `code/app/core/tickets/__init__.py`.
    - `code/app/core/tickets_service.py`:
      - migra a fuente única importando módulos internos de roles/workflow.
      - mantiene firmas/contratos públicos existentes (`normalize_*`, `_ensure_*`, transición, etc.) mediante wrappers compatibles.
    - `code/app/api/routers/tks.py`:
      - elimina duplicación de matriz de roles y consume la política centralizada.
  - Hardening frontend:
    - `code/static/modulos/tks/js/tks_ui.js`:
      - corrige XSS puntual en `renderCustomer360` escapando `customer_id` antes de interpolarlo en `onclick`.
    - `code/static/modulos/tks/js/tks_main.js`:
      - elimina dependencia de `event` global en `generatePaymentLink`.
      - la acción ahora recibe referencia explícita del botón (`this`) desde UI.
  - Pruebas de regresión nuevas:
    - `tests/unit_ticketera_core.py`:
      - matriz de permisos por rol (admin vs técnico, combinaciones de roles, asignación).
      - workflow y compatibilidad legacy (`triage`, reapertura, cierre directo legacy).
      - validación de wrappers en `tickets_service`.
    - `tests/unit_ticketera_frontend_security.py`:
      - asegura escape de `customer_id` en botón de pago.
      - asegura ausencia de uso de `event` global en `generatePaymentLink`.
    - `.github/workflows/deploy.yml`:
      - agrega ejecución de ambos tests unitarios en job `tests`.
- Verificación:
  - Baseline (pre-refactor):
    - `python3 tests/verify_hardening.py --check-api` PASS.
    - `python3 tests/e2e_api_full.py` PASS.
    - `python3 tests/e2e_ticketera.py` PASS.
  - Post-cambios:
    - sintaxis Python (`compile`) PASS:
      - `code/app/core/tickets_service.py`
      - `code/app/core/tickets/roles.py`
      - `code/app/core/tickets/workflow.py`
      - `code/app/api/routers/tks.py`
      - `tests/unit_ticketera_core.py`
      - `tests/unit_ticketera_frontend_security.py`
    - `node --check` PASS:
      - `code/static/modulos/tks/js/tks_ui.js`
      - `code/static/modulos/tks/js/tks_main.js`
    - `python3 tests/unit_ticketera_core.py` PASS.
    - `python3 tests/unit_ticketera_frontend_security.py` PASS.
    - `python3 tests/verify_hardening.py --check-api` PASS.
    - `python3 tests/e2e_api_full.py` PASS.
    - `python3 tests/e2e_ticketera.py` PASS.
- Estado: CERRADO.

### 2026-02-19 12:33 - EPIC 11 Ticketera: reset operativo de datos en DEV
- Solicitud: resetear ticketera sin afectar módulos no relacionados.
- Entregable:
  - limpieza de datos transaccionales en tablas de ticketera (manteniendo configuración):
    - truncadas con `RESTART IDENTITY CASCADE`:
      - `ticket_notification_attempts`, `ticket_notifications`, `ticket_email_draft_attachments`,
      - `ticket_email_drafts`, `ticket_attachments`, `ticket_emails`, `ticket_comments`,
      - `ticket_transitions`, `ticket_approvals`, `ticket_legal_holds`, `jira_issue_map`, `tickets`.
    - preservadas:
      - `ticket_config_client_emails`
      - `ticket_automation_rules`
  - limpieza de filesystem de adjuntos ticketera en DEV:
    - raíz: `/srv/monstruo_dev/data/tickets`
    - elementos removidos: `36`
- Verificación:
  - conteo post-reset en tablas truncadas: `0` registros.
  - API ticketera (`/api/tks/tickets?limit=5`) con autenticación bearer: `total=0`, `items=0`.
- Estado: CERRADO.

### 2026-02-19 17:40 - Homologación visual de tabs en módulos (altura + diseño unificado PMO)
- Solicitud: aplicar la misma corrección de altura y diseño de pestañas en todos los módulos para mantener homogeneidad.
- Entregable:
  - `code/static/modulos/tks/tks.html`:
    - header principal de Ticketera migra a `section-header module-tabs-header`.
    - barra de tabs Ticketera integra estándar compartido con clases `tab-bar` y `tab-btn` (manteniendo `tks-tab-*` para compatibilidad JS).
  - `code/static/modulos/tks/css/tks.css`:
    - se eliminan estilos visuales divergentes de tabs (fondo degradado y estado activo lleno) para heredar diseño PMO/ERP del CSS compartido.
    - se conserva posicionamiento relativo para badge de notificación en tabs.
  - `code/static/modulos/bodega/bodega.html`:
    - header de tabs migra a `section-header module-tabs-header` para igualar altura/espaciado con PMO/ERP.
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - regla canónica agrega neutralización de `::after` activo en tabs para eliminar subrayados legacy y mantener un solo patrón visual.
  - cache bust global de CSS compartido:
    - `monstruo.css?v=67.7` -> `monstruo.css?v=67.8` en módulos shell (`configuracion`, `pmo`, `erp`, `bodega`, `dashboard`, `zabbix`, `crm`, `ultron`, `tks`).
- Verificación:
  - revisión estructural en HTML/CSS por grep:
    - Ticketera y Bodega contienen `module-tabs-header`.
    - Ticketera tabs contienen `tab-bar` + `tab-btn`.
    - CSS compartido contiene neutralización `tab-btn.active::after`.
  - alcance funcional: sin cambios de contratos JS/API ni rutas.
- Estado: CERRADO.

### 2026-02-19 17:45 - Homologación de títulos principales en 9 módulos (mismo tamaño)
- Solicitud: dejar el título principal de cada página con el mismo tamaño en los 9 módulos.
- Entregable:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - nueva clase canónica `module-page-title` bajo `section-header`:
      - `font-size: 1.8rem` desktop.
      - `font-size: 1.5rem` en `max-width: 900px`.
      - normalización de `line-height`, `letter-spacing` y `text-transform`.
  - títulos principales marcados con `class="module-page-title"` en:
    - `code/static/modulos/dashboard/dashboard.html`
    - `code/static/modulos/configuracion/configuracion.html`
    - `code/static/modulos/crm/crm.html`
    - `code/static/modulos/erp/erp.html`
    - `code/static/modulos/pmo/pmo.html`
    - `code/static/modulos/bodega/bodega.html`
    - `code/static/modulos/tks/tks.html`
    - `code/static/modulos/ultron/ultron.html`
    - `code/static/modulos/zabbix/zabbix.html`
  - se removieron tamaños inline en títulos de `ERP`, `PMO` y `Bodega` para evitar divergencias futuras.
  - cache bust global del CSS compartido:
    - `monstruo.css?v=67.8` -> `monstruo.css?v=67.9`.
- Verificación:
  - grep de control confirma `module-page-title` presente en los 9 módulos objetivo.
  - grep de control confirma `monstruo.css?v=67.9` aplicado en todos los shells.
  - alcance funcional: cambio visual únicamente (sin modificación de contratos JS/API).
- Estado: CERRADO.

### 2026-02-19 17:49 - Ajuste fino Dashboard: header al mismo patrón de ERP/PMO
- Solicitud: alinear `Dashboard` con `ERP/PMO` para que título y texto inferior queden a la misma altura/patrón visual.
- Entregable:
  - `code/static/modulos/dashboard/dashboard.html`:
    - header principal de `section-general` migra a `section-header module-tabs-header`.
    - mismo override visual de `ERP/PMO` (`border:none; padding-bottom:0`).
    - título principal pasa a `<h2 class="module-page-title">Dashboard</h2>`.
    - texto inferior `#dashboard-status` permanece bajo el título con opacidad equivalente al patrón.
- Verificación:
  - revisión estructural en HTML:
    - `section-header module-tabs-header` presente en bloque principal de dashboard.
    - `#dashboard-status` conservado para compatibilidad con render dinámico JS.
  - alcance funcional: cambio visual únicamente (sin cambios en lógica/API).
- Estado: CERRADO.

### 2026-02-19 17:52 - Fix Dashboard: estado del servidor vuelve al costado derecho
- Solicitud: corregir bug visual donde el estado del server quedó debajo/encima del título en lugar de aparecer a la derecha.
- Entregable:
  - `code/static/modulos/dashboard/dashboard.html`:
    - header principal ajustado a dos columnas lógicas:
      - bloque izquierdo: título + subtítulo estático.
      - bloque derecho: `#dashboard-status` dinámico.
    - `#dashboard-status` mantiene el mismo ID para compatibilidad total con `renderDashboardHeader(...)`.
    - estilos locales nuevos para:
      - `.dashboard-header-meta`
      - `.dashboard-header-subtitle`
      - `.dashboard-server-status` (alineación a la derecha en desktop; izquierda en mobile).
- Verificación:
  - revisión HTML confirma `#dashboard-status` fuera del bloque de título y posicionado como sibling derecho.
  - compatibilidad JS preservada: la función que escribe estado sigue apuntando al mismo `id`.
  - alcance funcional: corrección visual únicamente.
- Estado: CERRADO.

### 2026-02-19 17:54 - Ajuste fino CRM: título a misma altura y subtítulo alineado al estándar
- Solicitud: dejar `CRM` con título a la misma altura que ERP/PMO y con subtítulo acorde.
- Entregable:
  - `code/static/modulos/crm/crm.html`:
    - header principal migra a `section-header module-tabs-header` con override visual (`border:none; padding-bottom:0`) igual al patrón ERP/PMO.
    - título principal pasa a `<h2 class="module-page-title">Gestión de Clientes</h2>`.
    - subtítulo actualizado a `Gestión centralizada de clientes y cartera comercial`, ubicado bajo el título en bloque interno.
- Verificación:
  - revisión estructural del header confirma patrón: `module-tabs-header` + wrapper interno para título/subtítulo.
  - alcance funcional: cambio visual únicamente (sin cambios en lógica/API).
- Estado: CERRADO.

### 2026-02-19 17:58 - Ajuste CRM: estructura de header igual a ERP/PMO (alineación fina)
- Solicitud: corregir diferencia visual ligera de CRM respecto a ERP/PMO.
- Entregable:
  - `code/static/modulos/crm/crm.html`:
    - se mueve el header principal (`section-header module-tabs-header`) fuera del `section-block`, igual al patrón estructural de ERP/PMO.
    - `section-block` de contenido queda separado y con `padding:0` para eliminar offset lateral/superior extra.
    - se mantiene título/subtítulo definidos en el ajuste anterior.
- Verificación:
  - revisión de estructura confirma:
    - header principal en `main-inner` como sibling del bloque de contenido.
    - contenido operativo (buscador + tabla) dentro de `section-block` sin padding.
  - alcance funcional: cambio visual/maquetación únicamente (sin cambios JS/API).
- Estado: CERRADO.

### 2026-02-19 18:00 - Ajuste Ticketera: misma línea visual que ERP/PMO/CRM
- Solicitud: comparar y ajustar Mesa de Ayuda para seguir la misma línea de diseño que los demás módulos.
- Entregable:
  - `code/static/modulos/tks/tks.html`:
    - header principal se mueve fuera de `section-block`, quedando como sibling directo en `main-inner` (igual patrón ERP/PMO).
    - título principal normalizado a `h2.module-page-title` sin emoji para homogeneidad visual.
    - subtítulo principal actualizado y alineado bajo el título.
    - `tab-bar` mantiene posición inmediatamente bajo el header (patrón estándar).
    - contenido dinámico de ticketera queda en `section-block` separado con `padding:0` para eliminar offset extra.
    - se preservan IDs/acciones de UI (`#tks-view-badge`, `#tks-notif-badge`, `#tks-create-btn`) para compatibilidad total con JS.
- Verificación:
  - revisión estructural confirma secuencia: `header principal` -> `tab-bar` -> `section-block contenido`.
  - búsqueda de contratos UI confirma que IDs usados por `tks_main.js` siguen intactos.
  - alcance funcional: solo ajuste visual/maquetación (sin cambios de lógica/API).
- Estado: CERRADO.

### 2026-02-19 18:02 - Ticketera: retiro de badge de rol bajo subtítulo
- Solicitud: quitar texto de rol/vista (`Admin Gestión · ADMIN`) que aparecía debajo del subtítulo en cabecera.
- Entregable:
  - `code/static/modulos/tks/tks.html`:
    - se elimina el nodo `#tks-view-badge` del bloque bajo subtítulo para limpiar la cabecera.
- Verificación:
  - `tks_main.js` ya contiene guarda null-safe (`if (viewBadge) ...`), por lo que la ausencia del nodo no genera error de ejecución.
  - alcance funcional: cambio visual únicamente.
- Estado: CERRADO.

### 2026-02-19 18:04 - Homologación final de cabeceras en módulos restantes (IA, Zabbix, Configuración)
- Solicitud: aplicar la misma línea visual del header en los módulos faltantes (`IA/ULTRON`, `ZABBIX`, `CONFIGURACIONES`).
- Entregable:
  - `code/static/modulos/ultron/ultron.html`:
    - header principal migrado a `section-header module-tabs-header` fuera del `section-block`.
    - título normalizado a `h2.module-page-title`.
    - subtítulo con opacidad estándar (`0.6`) bajo el título.
    - contenido principal en `section-block` separado con `padding:0`.
  - `code/static/modulos/zabbix/zabbix.html`:
    - mismo patrón estructural: header principal separado + `h2.module-page-title` + subtítulo estándar.
    - bloque de contenido en `section-block` con `padding:0`.
  - `code/static/modulos/configuracion/configuracion.html`:
    - cabecera principal de Configuración movida fuera del bloque de contenido.
    - título principal migrado a `h2.module-page-title`.
    - subtítulo en formato estándar.
    - sección de contenido principal (`SMTP`) queda en `section-block` separado con `padding:0`.
- Verificación:
  - revisión estructural confirma presencia de `module-tabs-header` y `module-page-title` en los 3 módulos.
  - alcance funcional: ajustes de presentación/maquetación únicamente (sin cambios JS/API).
- Estado: CERRADO.

### 2026-02-19 18:17 - Estructura única de shell para 9 módulos (ancho/maquetación unificados)
- Solicitud: dejar una sola estructura base para los módulos y eliminar diferencias de ancho/percepción visual.
- Entregable:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - nuevas clases canónicas de shell:
      - `.module-shell-header`
      - `.module-shell-title`
      - `.module-shell-subtitle`
      - `.module-shell-actions`
      - `.section-block.module-shell-content`
      - `.section-block.module-shell-content.module-shell-content-fill`
    - ajuste responsive para acciones de cabecera en mobile.
  - unificación estructural (top-level shell) en:
    - `code/static/modulos/dashboard/dashboard.html`
    - `code/static/modulos/configuracion/configuracion.html`
    - `code/static/modulos/crm/crm.html`
    - `code/static/modulos/erp/erp.html`
    - `code/static/modulos/pmo/pmo.html`
    - `code/static/modulos/bodega/bodega.html`
    - `code/static/modulos/tks/tks.html`
    - `code/static/modulos/ultron/ultron.html`
    - `code/static/modulos/zabbix/zabbix.html`
  - cambios estructurales clave:
    - `main-inner` normalizado a `class="main-inner module-shell"` en los 9 módulos.
    - cabecera principal normalizada a `section-header module-tabs-header module-shell-header`.
    - título/subtítulo normalizados con `module-shell-title` + `module-shell-subtitle`.
    - bloque principal de contenido normalizado con `section-block module-shell-content`.
  - corrección de ancho inconsistente:
    - se elimina override local de PMO (`.main-inner { max-width: 1200px; }`) para volver al ancho canónico compartido (`--max-content-width`).
  - guía visual en dashboard actualizada para reflejar el nuevo patrón único de shell.
  - cache-bust global:
    - `monstruo.css?v=67.9` -> `monstruo.css?v=68.0` en módulos shell.
- Verificación:
  - chequeo por grep confirma en los 9 módulos:
    - `main-inner module-shell`: OK
    - `module-shell-header`: OK
    - `module-shell-content`: OK
  - chequeo por grep confirma eliminación del override `max-width: 1200px` en PMO.
  - alcance funcional: cambio de maquetación/estilo; sin cambios de contratos JS/API.
- Estado: CERRADO.

### 2026-02-19 19:02 - Ticketera: limpieza visual base y alineación de assets compartidos
- Solicitud: concentrar trabajo en Ticketera manteniendo homogeneidad visual con el resto de módulos.
- Entregable:
  - `code/static/modulos/tks/tks.html`
    - cache-bust de estilos Ticketera: `tks.css?v=38`.
    - assets compartidos alineados con estándar actual:
      - `admin.js?v=4`
      - `sidebar.js?v=11`
    - campana de notificaciones sin inline styles (usa clases CSS).
  - `code/static/modulos/tks/css/tks.css`
    - limpieza de duplicaciones internas sin cambio de comportamiento:
      - comentarios duplicados al inicio.
      - bloques repetidos de `.tks-feed-content`, `.tks-feed-title`, `.tks-feed-detail`.
      - bloque conflictivo anterior de `.tks-feed-foot` en `display:none`.
      - definiciones repetidas antiguas de `.tks-btn-sm` y `.tks-btn-icon`.
    - clases nuevas para notificación:
      - `.tks-notif-icon`
      - estado base oculto de `.tks-notif-count` (la visibilidad la sigue controlando `tks_main.js`).
- Verificación:
  - estructura shell de Ticketera se mantiene (`module-shell`, `module-shell-header`, `module-shell-content`).
  - `tks_main.js` sigue mostrando/ocultando badge con `badge.style.display = notifCount > 0 ? 'flex' : 'none'`.
  - alcance funcional: cambios de presentación/orden de CSS, sin cambio de contratos API.
- Estado: CERRADO.

### 2026-02-19 19:05 - Ticketera: Resumen con Asignación Técnica en formato cuadro
- Solicitud: en la vista `Resumen` de Ticketera, la sección de `Asignación Técnica` debe verse como un cuadro/card.
- Entregable:
  - `code/static/modulos/tks/css/tks.css`
    - `.tks-dashboard-assignment` ahora tiene:
      - fondo (`var(--tks-bg-secondary)`)
      - borde (`1px solid var(--tks-border)`)
      - radio (`12px`)
      - padding interno
      - sombra suave
  - `code/static/modulos/tks/tks.html`
    - cache-bust de estilo actualizado a `tks.css?v=39`.
- Verificación:
  - la tarjeta de `Asignación Técnica` queda encapsulada visualmente solo en `Resumen`.
  - la vista de `Asignación` como pestaña independiente mantiene su layout original.
- Estado: CERRADO.

### 2026-02-19 19:10 - Ticketera: ajuste integral de pestaña Lista (UI limpia y consistente)
- Solicitud: arreglar la pestaña `Lista` de Ticketera.
- Entregable:
  - `code/static/modulos/tks/js/tks_main.js`
    - limpieza de render de Lista:
      - toolbar para técnico con clase (`.tks-toolbar-note`) en vez de inline style.
      - filtro de estado con modificador `.tks-filter-row--status` (sin inline style).
      - skeletons de carga con clase `.tks-list-skeleton`.
      - estado vacío y error con clases (`.tks-list-empty`, `.tks-list-error`).
      - panel detalle inicial sin `style="display:none"` inline (usa CSS base).
  - `code/static/modulos/tks/js/tks_ui.js`
    - tabla Lista renderizada con clases semánticas en vez de estilos inline:
      - títulos/cliente/email origen (`.tks-ticket-title`, `.tks-client-name`, `.tks-origin-email`).
      - celda SLA por estado (`.tks-sla-cell.is-breached|is-warning|is-ok`).
      - columna creado/acciones (`.tks-created-cell`, `.tks-action-cell`).
      - anchos de encabezado por clase (`.tks-th-*`).
  - `code/static/modulos/tks/css/tks.css`
    - estilos nuevos para el layout de Lista y sus estados.
    - `tks-list-layout` reforzado como bloque visual consistente (borde + radio).
  - `code/static/modulos/tks/tks.html`
    - cache-bust actualizado:
      - `tks.css?v=40`
      - `tks_ui.js?v=68`
      - `tks_main.js?v=44`
- Verificación:
  - `node --check code/static/modulos/tks/js/tks_main.js` -> PASS.
  - `node --check code/static/modulos/tks/js/tks_ui.js` -> PASS.
  - alcance funcional: no cambia contratos API ni lógica de filtros/navegación; ajuste visual/estructural de render.
- Estado: CERRADO.

### 2026-03-23 17:08 - EPIC 11 Ticketera: configuración autónoma, reply directo y Kanban secuencial
- Solicitud: implementar el plan de Antigravity para EPIC 11 en Ticketera.
- Entregable:
  - Backend Ticketera:
    - `code/app/core/db.py`
      - creación canónica de `ticket_config_client_emails`.
      - nueva tabla `ticket_config_email_routes` para routing por correo/dominio.
    - `code/app/core/tickets_service.py`
      - templates de auto-respuesta configurables desde `system_settings`.
      - CRUD y resolución de routing por correo/dominio con prioridad `email > domain > clasificación`.
      - reply al cliente bloqueado salvo en `en_progreso`.
      - helper unificado de correo saliente sin firma legacy y con adjuntos persistidos.
      - asunto de reply canónico y movimientos principales de estado restringidos a un paso por vez.
    - `code/app/api/routers/config_router.py`
      - nuevos endpoints `/api/config/ticketera`, `/api/config/ticketera/templates`, `/api/config/ticketera/routing-rules`.
    - `code/app/api/routers/tks.py`
      - `reply-email` acepta `to_addr`, `cc_addrs`, `bcc_addrs` desde el composer directo.
  - Frontend Ticketera:
    - `code/static/modulos/configuracion/configuracion.html`
      - UI para editar plantilla de auto-respuesta y reglas de enrutamiento por correo/dominio.
    - `code/static/modulos/tks/js/tks_ui.js`
      - composer directo sin `guardar/descartar borrador`.
      - asunto readonly, adjuntos locales y acción de respuesta habilitada solo en `en_progreso`.
      - mensaje guía bajo avance de flujo: `Para responder el ticket al cliente, debes pasarlo primero a estado En Progreso`.
      - Kanban con drag validado por estado adyacente.
    - `code/static/modulos/tks/js/tks_main.js`
      - `openDetail()` deja de consumir `email-draft*`.
      - confirmación previa al envío usando `reply-email` con `FormData`.
      - detección de cambios pendientes basada en valores actuales del form y archivos locales.
  - Pruebas:
    - `tests/unit_ticketera_core.py`
      - cobertura de routing, templates, bloqueo de reply, transición secuencial y helper de correo saliente.
    - `tests/e2e_ticketera.py`
      - ampliado para bloqueo reply fuera de `en_progreso`, asunto canónico, ausencia de firma legacy, `409` por salto de estado, routing configurable y templates de auto-respuesta.
- Verificación:
  - `python3 -m compileall -q code/app tests/unit_ticketera_core.py tests/e2e_ticketera.py` -> PASS.
  - `python3 -m py_compile code/app/api/routers/config_router.py code/app/api/routers/tks.py code/app/core/tickets_service.py` -> PASS.
  - `python3 -m unittest tests.unit_ticketera_core` -> PASS (`20` tests).
  - `node --check code/static/modulos/tks/js/tks_ui.js` -> PASS.
  - `node --check code/static/modulos/tks/js/tks_main.js` -> PASS.
  - `node --check code/static/modulos/tks/js/tks_api.js` -> PASS.
  - `python3 tests/e2e_ticketera.py` -> BLOQUEADO por entorno: faltan `MONSTRUO_TEST_USER` y `MONSTRUO_TEST_PASSWORD`.
- Estado: CERRADO.

### 2026-04-01 15:37 - Login centralizado y corte limpio DEV/PROD en módulos
- Solicitud: eliminar el login local de Ticketera como entrada pública y forzar redirección al login central, usando `/dev` solo en desarrollo y sin arrastrar marcas de `dev` a producción.
- Entregable:
  - `plataforma/core/web.py`
    - helper centralizado para construir redirects de login con detección robusta de prefijo público (`x-forwarded-prefix`, `x-original-uri`, `referer`, `root_path`).
    - login canónico definido como `/login` tanto en PROD como en DEV.
  - `gateway/main.py`
    - `dashboard` y `configuracion` sin sesión ahora redirigen al login central.
    - `fundacion` sin permisos/sesión también rebota al login central.
  - `ticketera/main.py`
    - `GET /` sin sesión ya no muestra `ticketera/ui/login.html`; ahora responde `302` al login central.
    - `GET /login.html` quedó como redirect al login central.
  - `erp/main.py`, `bodega/main.py`, `crm/main.py`, `pmo/main.py`, `ia/main.py`, `zabbix/main.py`, `fundacion/main.py`
    - raíz protegida con `require_session_hybrid` y redirect al login central cuando no existe sesión.
  - `gateway/shared/ui/js/utilidades.js`
    - `LOGIN_URL` canónico:
      - PROD -> `https://login.telconsulting.cl/login`
      - DEV -> `https://login.telconsulting.cl/dev/login`
    - lógica de entorno reducida a `'/dev'` o `''` (sin `/prod`).
  - `gateway/shared/ui/js/sidebar.js`
    - eliminado el comportamiento que exponía `IR A DEV` en producción.
    - el botón `VOLVER A PROD` solo aparece cuando realmente se navega dentro de `DEV`.
- Verificación:
  - compilación sin bytecode de Python sobre `plataforma/core/web.py`, `gateway/main.py`, `ticketera/main.py`, `erp/main.py`, `bodega/main.py`, `crm/main.py`, `pmo/main.py`, `ia/main.py`, `zabbix/main.py`, `fundacion/main.py` -> PASS.
  - `node --check gateway/shared/ui/js/utilidades.js` -> PASS.
  - `node --check gateway/shared/ui/js/sidebar.js` -> PASS.
  - `docker compose --env-file plataforma/ops/env/.env.server.dev config -q` -> PASS (warning conocido: `version` obsoleto).
  - smoke test helper `build_login_redirect_url`:
    - PROD -> `https://login.telconsulting.cl/login`
    - DEV con `x-forwarded-prefix=/dev` -> `https://login.telconsulting.cl/dev/login`
    - DEV con `x-original-uri=/dev/` -> `https://login.telconsulting.cl/dev/login`
    - local -> `http://127.0.0.1:9001/login`
  - smoke test rutas:
    - `ticketera /` sin sesión -> `302 https://login.telconsulting.cl/dev/login`
    - `ticketera /login.html` -> `302 https://login.telconsulting.cl/dev/login`
    - `gateway /dashboard` sin sesión -> `302 https://login.telconsulting.cl/dev/login`
    - `gateway /configuracion` sin sesión -> `302 https://login.telconsulting.cl/dev/login`
  - `gateway /login`, `/`, `/login/login.html` en subdominio login -> `200 text/html`
- Estado: CERRADO.

### 2026-04-01 15:43 - Diagnóstico público `login.telconsulting.cl/dev/`: 404 en proxy, no en backend
- Solicitud: revisar por qué `https://login.telconsulting.cl/dev/` seguía dando `404` después del ajuste de login central.
- Hallazgo:
  - el backend `gateway` en esta VM responde correctamente la raíz DEV y las rutas de login bajo prefijo `/dev`.
  - el `404` público actual lo entrega `nginx`, antes de llegar a FastAPI.
  - esta sesión corre en la VM app `192.168.60.5`; la documentación de despliegue mantiene el proxy inverso en `192.168.60.6`.
- Verificación:
  - `hostname -I` en esta sesión -> `192.168.60.5` ✅
  - smoke local con `TestClient` sobre `gateway`:
    - `/` -> `200 text/html` ✅
    - `/dev/` -> `200 text/html` ✅
    - `/login` -> `200 text/html` ✅
    - `/dev/login` -> `200 text/html` ✅
    - `/dashboard` -> `302 https://login.telconsulting.cl/dev/login` ✅
    - `/dev/dashboard` -> `302 https://login.telconsulting.cl/dev/login` ✅
  - validación pública:
    - `curl -k -I https://login.telconsulting.cl/dev/` -> `HTTP/2 404`, `server: nginx/1.22.1` ✅
    - `curl -k -I https://login.telconsulting.cl/dev/login` -> `HTTP/2 404`, `server: nginx/1.22.1` ✅
    - `curl -k -I https://login.telconsulting.cl/dev/dashboard` -> `HTTP/2 404`, `server: nginx/1.22.1` ✅
- Conclusión:
  - el problema vigente está en la publicación del proxy público para `login.telconsulting.cl` en la VM `192.168.60.6`.
  - la app nueva ya quedó lista para responder esas rutas si el proxy las reenvía correctamente.
- Estado: DIAGNÓSTICO CONFIRMADO. PENDIENTE AJUSTE/RECARGA EN PROXY PÚBLICO.

### 2026-04-01 15:52 - Fix aplicado en proxy público para `login.telconsulting.cl/dev/` + reparación de assets en `gateway`
- Solicitud: entrar a la VM proxy `192.168.60.6` como `root`, corregir el `404` público de `https://login.telconsulting.cl/dev/` y dejar el login DEV operativo.
- Acción ejecutada:
  - Proxy público `192.168.60.6`:
    - se inspeccionó `login.telconsulting.cl.conf` y se confirmó que `location /dev/` estaba heredándose desde `monstruo_dev_locations.conf` hacia `http://192.168.60.5:80`, capa intermedia que para el host `login.telconsulting.cl` devolvía `404`.
    - se respaldó `/etc/nginx/sites-available/login.telconsulting.cl.conf` en:
      - `/etc/nginx/sites-available/login.telconsulting.cl.conf.bak.login-dev-direct.20260401_185017`
    - se reemplazó el include DEV genérico por un `location /dev/` dedicado para `login.telconsulting.cl`, apuntando directo a `http://192.168.60.5:9001/` con `X-Forwarded-Prefix /dev`.
    - se validó `nginx -t` y se recargó Nginx en la VM proxy.
  - Backend `gateway`:
    - se detectó que el HTML de login ya salía, pero los assets `/login/...`, `/dashboard/...`, `/configuracion/...` y `/shared/...` estaban cayendo en `404` desde FastAPI.
    - en `gateway/main.py` se reemplazaron los mounts estáticos problemáticos por rutas explícitas con `FileResponse`:
      - `/dashboard/{asset_path:path}`
      - `/configuracion/{asset_path:path}`
      - `/login/{asset_path:path}`
      - `/shared/{asset_path:path}`
- Verificación:
  - local VM app `192.168.60.5`:
    - `curl -H 'Host: login.telconsulting.cl' http://127.0.0.1/dev/` -> `404 nginx` en la capa local `:80` ✅ causa confirmada
    - `curl -H 'Host: login.telconsulting.cl' http://127.0.0.1:9001/` -> `200` HTML login ✅
  - proxy público tras fix:
    - `https://login.telconsulting.cl/dev/` -> `200` HTML login con `<base href="/dev/login/">` ✅
    - `https://login.telconsulting.cl/dev/login` -> `200` HTML login ✅
    - `https://login.telconsulting.cl/dev/dashboard` sin sesión -> `302 https://login.telconsulting.cl/dev/login` ✅
    - `https://login.telconsulting.cl/dev/login/js/login.js` -> `200` JS ✅
    - `https://login.telconsulting.cl/dev/shared/js/utilidades.js` -> `200` JS ✅
    - `https://login.telconsulting.cl/dev/login/css/login.css` -> `200` CSS ✅
  - Python:
    - `compile(...)` sobre `gateway/main.py` -> PASS.
- Estado: APLICADO Y VALIDADO EN DEV. `login.telconsulting.cl/dev/` vuelve a abrir correctamente y ya no depende del Nginx local roto de `192.168.60.5:80`.

### 2026-04-01 15:56 - Canon de login ajustado a raíz del subdominio
- Solicitud: mantener siempre el login central en la raíz del dominio de acceso, sin derivar a `/login`, para preservar la separación por subdominios (`login`, `ticketera`, `erp`, etc.) y evitar URLs con variaciones innecesarias.
- Acción ejecutada:
  - `plataforma/core/web.py`
    - `build_login_redirect_url()` vuelve a considerar canónico:
      - PROD -> `https://login.telconsulting.cl/`
      - DEV -> `https://login.telconsulting.cl/dev/`
    - fallback local:
      - `http://127.0.0.1:9001/`
  - `gateway/shared/ui/js/utilidades.js`
    - `LOGIN_URL` vuelve a usar la raíz del subdominio de login:
      - prod -> `https://login.telconsulting.cl/`
      - dev -> `https://login.telconsulting.cl/dev/`
      - local -> `http://<host>:9001/` o `http://<host>:9001/dev/`
- Verificación:
  - helper local:
    - prod -> `https://login.telconsulting.cl/` ✅
    - dev -> `https://login.telconsulting.cl/dev/` ✅
    - local -> `http://127.0.0.1:9001/` ✅
  - flujo público:
    - `https://ticketera.telconsulting.cl/dev/` sin sesión -> `302 location: https://login.telconsulting.cl/dev/` ✅
    - `https://login.telconsulting.cl/dev/` -> `200` HTML login ✅
    - `https://login.telconsulting.cl/` -> `200` HTML login ✅
- Nota:
  - el HTML servido en raíz mantiene `<base href="/dev/login/">` en DEV y `<base href="/login/">` en PROD para resolver assets internos, pero la URL visible/canónica para el usuario queda en la raíz del subdominio, como se definió.
- Estado: APLICADO Y VALIDADO.

### 2026-04-01 19:55 - DEV subdominios: shared assets restaurados en `config` y `ticketera` + refresh de sidebar
- Solicitud: corregir `config` y `ticketera` en DEV porque se veían en blanco, y asegurar que el botón `Dashboard` del sidebar se mantuviera en DEV en vez de irse a PROD.
- Hallazgo:
  - `config.telconsulting.cl/dev/` sí entregaba HTML y su JS propio (`users_ui.js`), pero fallaban los assets compartidos:
    - `/dev/shared/css/monstruo.css` -> `404 nginx`
    - `/dev/shared/js/admin.js` -> `404 nginx`
    - `/dev/shared/js/sidebar.js` -> `404 nginx`
  - `ticketera.telconsulting.cl/dev/` tenía el mismo patrón para `shared/*`:
    - `/dev/shared/js/utilidades.js` -> `404 nginx`
    - `/dev/shared/css/monstruo.css` -> `404 nginx`
    - mientras `static/js/tks_main.js` sí respondía `200`.
  - causa: el proxy público en `192.168.60.6` delegaba `/dev/` al Nginx intermedio de `192.168.60.5:80`, pero no tenía una excepción para `/dev/shared/` apuntando al `gateway` nuevo (`:9001/shared/`).
- Acción ejecutada:
  - Proxy público `192.168.60.6`:
    - se respaldó `/etc/nginx/snippets/monstruo_dev_locations.conf` en:
      - `/etc/nginx/snippets/monstruo_dev_locations.conf.bak.shared-dev.20260401_195439`
    - se agregó `location /dev/shared/` directo a `http://192.168.60.5:9001/shared/`
    - se mantuvo `location /dev/` legacy para las raíces de módulos
    - `nginx -t` + reload -> OK
  - Cache-bust frontend:
    - se subió `utilidades.js` de `v=207` a `v=208`
    - se subió `sidebar.js` de `v=20` a `v=21`
    - HTMLs activos actualizados:
      - `gateway/configuracion/configuracion.html`
      - `gateway/login/login.html`
      - `gateway/dashboard/inicio.html`
      - `gateway/dashboard/dashboard.html`
      - `ticketera/ui/tks.html`
      - `erp/ui/erp.html`
      - `bodega/ui/bodega.html`
      - `crm/ui/crm.html`
      - `pmo/ui/pmo.html`
      - `ia/ui/ia.html`
      - `zabbix/ui/zabbix.html`
      - `fundacion/ui/fundacion.html`
- Verificación:
  - `https://config.telconsulting.cl/dev/shared/css/monstruo.css` -> `200` ✅
  - `https://config.telconsulting.cl/dev/shared/js/sidebar.js` -> `200` ✅
  - `https://config.telconsulting.cl/dev/shared/js/admin.js` -> `200` ✅
  - `https://ticketera.telconsulting.cl/dev/shared/js/utilidades.js` -> `200` ✅
  - `https://ticketera.telconsulting.cl/dev/shared/css/monstruo.css` -> `200` ✅
  - `https://config.telconsulting.cl/dev/` publica ya:
    - `../shared/js/utilidades.js?v=208`
    - `../shared/js/sidebar.js?v=21`
  - el `sidebar.js` servido públicamente sigue construyendo `Dashboard` con:
    - `https://login.telconsulting.cl${envPrefix}/dashboard/`
    - y `envPrefix` depende de `window.getEnvPrefix()` / `pathname.startsWith('/dev')`
- Estado: APLICADO Y VALIDADO. Se corrige la causa de pantalla en blanco por assets compartidos faltantes y se fuerza recarga de la versión nueva del sidebar para evitar navegación a PROD por caché vieja.

### 2026-04-01 20:09 - Hotfix Dashboard DEV: conservar `/dev` en canonical redirect y menú
- Solicitud: al apretar `Dashboard` desde DEV, el navegador terminaba en `https://login.telconsulting.cl/` o `https://login.telconsulting.cl/dashboard` si existía sesión productiva.
- Hallazgo:
  - el sidebar estaba apuntando a `https://login.telconsulting.cl/dev/dashboard/`
  - `gateway/main.py` respondía `GET /dashboard/` con `RedirectResponse("/dashboard")`
  - ese redirect absoluto perdía el prefijo `/dev`, por lo que el navegador caía al dashboard de PROD o al login raíz de PROD.
- Acción ejecutada:
  - `gateway/main.py`
    - nuevo helper `_prefixed_path(request, path)`
    - `dashboard_canonical_redirect()` ahora responde con el prefijo público correcto:
      - DEV -> `/dev/dashboard`
      - PROD -> `/dashboard`
  - `gateway/shared/ui/js/sidebar.js`
    - el link de `Dashboard` se normalizó a `https://login.telconsulting.cl${envPrefix}/dashboard` (sin slash final)
  - cache-bust de `sidebar.js` subido a `v=22` en las UIs activas para forzar navegación con la versión nueva.
- Verificación:
  - `compile(...)` sobre `gateway/main.py` -> PASS.
  - `node --check gateway/shared/ui/js/sidebar.js` -> PASS.
  - `https://login.telconsulting.cl/dev/dashboard/` -> `302 location: /dev/dashboard` ✅
  - `https://ticketera.telconsulting.cl/dev/shared/js/sidebar.js?v=22` contiene:
    - `https://login.telconsulting.cl${envPrefix}/dashboard` ✅
- Estado: APLICADO Y VALIDADO. El acceso a `Dashboard` desde DEV ya no debe botar el prefijo ni caer en PROD por redirect canónico.

### 2026-04-02 - Modal de cambio de contraseña reparado en DEV y PROD
- Solicitud: arreglar la ventana de `Cambiar Contraseña` en ambos entornos.
- Hallazgo:
  - las pantallas activas sí exponían el botón `btn-open-change-password`, pero no existía ningún `#modal-change-password` en el DOM.
  - `initModal()` en `utilidades.js` dependía de que el modal ya estuviera escrito en cada HTML, por lo que el click en `Cuenta` no podía abrir nada.
  - en PROD coexistían dos copias activas del shared JS:
    - `gateway/shared/ui/js/utilidades.js`
    - `static_ui/modulos/_compartido/js/utilidades.js`
- Acción ejecutada:
  - `gateway/shared/ui/js/utilidades.js` en DEV:
    - nuevo helper `ensureChangePasswordModal()` que crea el modal en runtime si no existe.
    - `initModal()` ahora:
      - asegura el modal antes de bindear eventos
      - soporta cerrar por botón, click en backdrop y tecla `Escape`
      - reutiliza el mismo submit contra `/auth/change-password`
  - PROD:
    - mismo fix replicado en:
      - `/srv/monstruo/gateway/shared/ui/js/utilidades.js`
      - `/srv/monstruo/static_ui/modulos/_compartido/js/utilidades.js`
  - Cache-bust para forzar recarga:
    - DEV: `utilidades.js?v=209`
    - PROD: `utilidades.js?v=207`
    - actualizado en las UIs activas de `dashboard`, `configuracion`, `ticketera` y módulos que cargan el shared actual.
- Verificación:
  - `node --check /srv/monstruo_dev/gateway/shared/ui/js/utilidades.js` -> PASS.
  - `node --check /srv/monstruo/gateway/shared/ui/js/utilidades.js` -> PASS.
  - `node --check /srv/monstruo/static_ui/modulos/_compartido/js/utilidades.js` -> PASS.
  - público:
    - `https://login.telconsulting.cl/` ya publica `utilidades.js?v=207` ✅
    - `https://login.telconsulting.cl/dev/` ya publica `utilidades.js?v=209` ✅
  - referencias actualizadas:
    - PROD:
      - `/srv/monstruo/gateway/dashboard/dashboard.html` -> `v=207` ✅
      - `/srv/monstruo/gateway/configuracion/configuracion.html` -> `v=207` ✅
      - `/srv/monstruo/ticketera/ui/tks.html` -> `v=207` ✅
    - DEV:
      - `/srv/monstruo_dev/gateway/dashboard/dashboard.html` -> `v=209` ✅
      - `/srv/monstruo_dev/gateway/configuracion/configuracion.html` -> `v=209` ✅
  - `/srv/monstruo_dev/ticketera/ui/tks.html` -> `v=209` ✅
- Estado: APLICADO. El modal ya no depende de markup duplicado en cada HTML; si una pantalla carga `utilidades.js` nuevo y tiene botón `Cuenta`, el modal se genera y se puede abrir.

### 2026-04-02 - DEV: shell responsivo endurecido para zoom alto y móvil
- Solicitud: mejorar cómo se adapta la UI al zoom del navegador y al celular, porque el shell compartido y Ticketera/Configuración se desordenaban al entrar en breakpoints estrechos.
- Hallazgo:
  - el problema no era `viewport`; las pantallas activas ya lo tenían.
  - la causa principal estaba en `gateway/shared/ui/css/monstruo.css`:
    - `body.sidebar-collapsed` seguía mandando en móvil y ocultaba texto/brand.
    - existían dos bloques responsive peleados (`900px` y `768px`) con reglas duras como `position: fixed`, `height: 60px`, `display: none` y header icónico.
    - al subir mucho el zoom, el navegador caía en esos breakpoints y la UI quedaba “modo móvil roto”.
  - `gateway/configuracion/configuracion.html` todavía tenía un grid inline de 3 columnas para automatizaciones, lo que pisaba los `@media`.
  - `ticketera/ui/css/tks.css` seguía conservando tamaños rígidos:
    - altura mínima global muy alta
    - modal base con ancho fijo `560px`
    - tablas sin contenedor horizontal
- Acción ejecutada:
  - `gateway/shared/ui/css/monstruo.css`
    - se agrega `text-size-adjust` y `max-width: 100%` para media embebida.
    - se agregan `min-width: 0` a contenedores shell para evitar desbordes por flex/grid.
    - se reemplaza el responsive conflictivo por una sola lógica estable:
      - en `<=900px`, el sidebar colapsado deja de dominar.
      - el header pasa a sticky vertical, con nav horizontal scrolleable, acciones envolventes y `main` sin márgenes laterales rígidos.
      - las tabs del shell pasan a scroll horizontal en vez de romper el layout.
      - modales compartidos se limitan a ancho útil real.
      - en `<=640px`, se compactan paddings y botones sin esconder contenido clave.
  - `gateway/configuracion/configuracion.html`
    - nuevo grid `cfg-grid--automation` para los 3 campos de automatización.
    - se elimina el `grid-template-columns` inline que impedía bajar correctamente a una columna.
  - `ticketera/ui/css/tks.css`
    - se reduce la altura mínima base del módulo.
    - en `<=900px`, se bajan mínimos del detalle/feed para evitar bloques desproporcionados.
    - en `<=640px`, formularios, stats, cards y modales pasan a una sola columna.
    - `tks-modal` deja de depender de ancho fijo y usa el viewport real.
    - `tks-table-wrapper` pasa a `overflow-x: auto` y `tks-table` gana `min-width` controlada para scroll horizontal limpio.
  - `gateway/dashboard/dashboard.html`
    - las tablas dinámicas de alertas, top clientes y correos pendientes quedan envueltas en `table-scroll` para móvil/zoom alto.
  - cache-bust:
    - `monstruo.css` -> `v=68.3` en apps activas del shell (`gateway/ticketera/erp/bodega/crm/pmo/ia/zabbix/fundacion`)
    - `ticketera/ui/tks.html` -> `tks.css?v=55`
- Verificación:
  - revisión directa de archivos modificados:
    - `gateway/shared/ui/css/monstruo.css` contiene un único responsive canónico con overrides explícitos para `body.sidebar-collapsed` en `<=900px` ✅
    - `gateway/configuracion/configuracion.html` ya usa `cfg-grid--automation` y no depende de inline grid de 3 columnas ✅
    - `ticketera/ui/css/tks.css` expone nuevo bloque `@media (max-width: 640px)` y wrapper horizontal para tabla ✅
  - assets públicos:
    - `https://ticketera.telconsulting.cl/dev/shared/css/monstruo.css?v=68.3` -> `200` ✅
    - `https://config.telconsulting.cl/dev/shared/css/monstruo.css?v=68.3` -> `200` ✅
    - `https://ticketera.telconsulting.cl/dev/static/css/tks.css?v=55` -> `200` ✅
  - referencias cache-bust:
    - `gateway/configuracion/configuracion.html` -> `monstruo.css?v=68.3` ✅
    - `gateway/dashboard/dashboard.html` -> `monstruo.css?v=68.3` ✅
    - `ticketera/ui/tks.html` -> `monstruo.css?v=68.3` y `tks.css?v=55` ✅
- Estado: APLICADO EN DEV. Queda mejor blindado para zoom alto, zoom bajo y móvil, especialmente en shell compartido, Configuración y Ticketera. No se hizo prueba manual con navegador autenticado dentro de Ticketera/Config; la validación fue por archivos reales y assets públicos expuestos.

### 2026-04-02 - DEV: menú móvil plegable para evitar header gigante
- Solicitud: en versión móvil los botones de la barra se ven demasiado grandes; se pide dejar un solo botón para expandir/ocultar el menú y que los accesos no ocupen espacio permanente.
- Hallazgo:
  - el responsive anterior seguía mostrando `side-nav` + `header-actions` completos en móvil.
  - el botón `#sidebar-toggle` estaba oculto justo en el breakpoint móvil, así que no existía una forma compacta de abrir/cerrar el shell.
- Acción ejecutada:
  - `gateway/shared/ui/js/sidebar.js`
    - el toggle ahora distingue escritorio vs móvil:
      - escritorio: sigue colapsando el sidebar normal.
      - móvil (`<=900px`): abre/cierra `body.mobile-sidebar-open`.
    - el icono del toggle cambia entre `bars` y `times`.
    - cerrar automático del menú móvil al:
      - tocar un link del menú
      - tocar `Cuenta` / `Salir` / `Volver a Prod`
      - tocar fuera del header
      - presionar `Escape`
  - `gateway/shared/ui/css/monstruo.css`
    - en móvil el header queda compacto por defecto.
    - `side-nav` y `header-actions` quedan ocultos mientras el menú no esté abierto.
    - al abrir, se muestran en columna y a ancho completo, sin ocupar espacio cuando están cerrados.
  - cache-bust:
    - `sidebar.js` -> `v=23`
    - `monstruo.css` -> `v=68.4`
    - actualizado en `gateway/ticketera/erp/bodega/crm/pmo/ia/zabbix/fundacion`
- Verificación:
  - `node --check gateway/shared/ui/js/sidebar.js` -> PASS ✅
  - referencias actualizadas:
    - `sidebar.js?v=23` en las UIs activas ✅
    - `monstruo.css?v=68.4` en las UIs activas ✅
  - assets públicos:
    - `https://ticketera.telconsulting.cl/dev/shared/js/sidebar.js?v=23` -> `200` ✅
    - `https://ticketera.telconsulting.cl/dev/shared/css/monstruo.css?v=68.4` -> `200` ✅
- Estado: APLICADO EN DEV. En móvil el shell ya no debería quedar desplegado todo el tiempo; ahora parte compacto y se abre solo cuando el usuario toca el botón menú.
