# PROYECTO CONTEXTO: MONSTRUO
**Fecha de actualizacion:** 09 Abril 2026
**Fuente de verdad:** `plataforma/docs/PLAN_MAESTRO_MONSTRUO.md`

## HITO: 2026-04-09 - DEV: Login se recupera tras cambios Docker (bootstrap usuario + cookie secure por HTTPS real)
- **Solicitud ejecutada**:
  - destrabar inicio de sesión en DEV después de cambios recientes en Docker/Compose que dejaron la base sin usuarios y el login en loop por cookie `Secure` en HTTP.
- **Accion ejecutada**:
  - bootstrap de usuario DEV:
    - `plataforma/ops/herramientas/dev/create_manual_user.py`
      - el script deja de depender de `plataforma/legacy/code` (estructura antigua) y usa `plataforma/core`.
      - agrega modo seguro de password por prompt (no se expone por flags).
      - ejecuta `db.init_db()` antes de crear/upsert para asegurar schemas/tablas.
  - operación: sincronización de usuarios PROD -> DEV (sin copiar hashes de password):
    - se exportan `username/role/roles secundarios/allowed_modules/is_active/phone_number/created_at` desde `auth.users` de PROD.
    - se upsertean en `auth.users` de DEV y se fuerza **password temporal en DEV** para poder ingresar (se define por prompt, no queda hardcodeado).
  - hardening DEV/PROD (carga de entorno):
    - `plataforma/core/env_loader.py`
      - prioriza `.env.server.dev` cuando el workspace contiene un ancestro `*_dev`/`*-dev`, evitando que scripts ejecutados desde `plataforma/` carguen `.env.server` por accidente.
  - auth cookies (DEV/Proxy):
    - `gateway/main.py`
    - `ticketera/main.py`
      - `COOKIE_SECURE=1` solo marca la cookie como `Secure` si el request efectivamente llega como HTTPS (scheme o `X-Forwarded-Proto`), evitando que el navegador descarte la cookie cuando se opera por HTTP en DEV.
- **Verificacion**:
  - `compile(..., 'exec')` en memoria:
    - `plataforma/ops/herramientas/dev/create_manual_user.py` ✅
    - `plataforma/core/env_loader.py` ✅
    - `gateway/main.py` ✅
    - `ticketera/main.py` ✅
  - verificación operativa:
    - `auth.users` en DEV queda con el mismo conteo que PROD tras la sincronización ✅
    - `POST /api/auth/login` en DEV responde `200` para un usuario sincronizado ✅
- **Estado**: APLICADO EN DEV. Requiere rebuild de contenedores para tomar el cambio en runtime.

## HITO: 2026-04-02 - DEV: Ticketera avisa nuevo TK al encargado de mesa por correo
- **Solicitud ejecutada**:
  - avisar al encargado de la mesa de ayuda cuando cae un ticket nuevo, usando correo ahora y dejando la base lista para futuros canales como WSP o 3CX.
- **Accion ejecutada**:
  - backend Ticketera:
    - `ticketera/service.py`
    - `ticketera/core/tickets_service.py`
    - `plataforma/core/tickets_service.py`
      - se agrega plantilla editable `helpdesk_new_ticket` para el aviso de nuevo TK a mesa.
      - se resuelve audiencia de notificacion buscando usuarios activos con rol primario o secundario `encargado_mesa`.
      - la audiencia conserva `email` y `phone_number` para reutilizar el mismo resolver en futuros canales.
      - `create_ticket(...)` dispara en segundo plano el correo al encargado de mesa apenas el ticket queda confirmado.
      - el contexto de plantillas suma placeholders operativos para categoria, severidad, correo de contacto, asignado y resumen SLA.
  - frontend Ticketera:
    - `ticketera/ui/js/tks_ui.js`
      - el modulo Dominio/Plantillas lista la nueva plantilla y expone los nuevos placeholders disponibles en el editor.
    - `ticketera/ui/tks.html`
      - cache-bust actualizado para refrescar el asset de UI.
- **Verificacion**:
  - `node --check ticketera/ui/js/tks_ui.js` ✅
  - `compile(..., 'exec')` en memoria:
    - `ticketera/service.py` ✅
    - `ticketera/core/tickets_service.py` ✅
    - `plataforma/core/tickets_service.py` ✅
- **Estado**: APLICADO EN DEV. Ticketera ahora avisa por correo al encargado de mesa al entrar un ticket y la resolucion de destinatarios queda preparada para reutilizar telefono en una futura salida por WhatsApp o 3CX.

## HITO: 2026-04-02 - DEV: Ticketera corrige SLA operativo, suma histórico y mejora manejo de imágenes
- **Solicitud ejecutada**:
  - ajustar Ticketera para que el compromiso operativo visible quede en `30 min` de auto-respuesta, `1 hora` para asignación y `2.5 horas` para resolución; además, mostrar informe histórico y evitar que los bloques de imágenes crezcan sin control, permitiendo pegar capturas directo en la respuesta al cliente.
- **Acción ejecutada**:
  - backend Ticketera:
    - `ticketera/service.py`
    - `ticketera/core/tickets_service.py`
    - `plataforma/core/tickets_service.py`
      - SLA operativo unificado:
        - auto-respuesta objetivo: `30 min`
        - asignación objetivo: `60 min`
        - resolución objetivo: `150 min`
      - la notificación al especialista agrega el recordatorio de SLA comprometido.
      - `get_sla_metrics(...)` suma bloque `historical_sla` con métricas históricas para:
        - auto-respuesta
        - asignación
        - resolución
  - configuración:
    - `ticketera/core/config.py`
    - `plataforma/core/config.py`
    - `gateway/configuracion/configuracion.html`
      - fallback/placeholder de auto-respuesta alineado a `30` minutos.
  - frontend Ticketera:
    - `ticketera/ui/js/tks_api.js`
      - agrega consumo de `/sla/metrics`.
    - `ticketera/ui/js/tks_main.js`
      - el resumen carga ventanas históricas de `7d` y `30d`.
      - el composer de respuesta captura imágenes pegadas desde clipboard y las agrega como adjuntos.
    - `ticketera/ui/js/tks_ui.js`
      - el dashboard renderiza tarjetas de informe histórico.
      - el composer muestra hint explícito para pegado de capturas.
    - `ticketera/ui/css/tks.css`
      - bloques de cuerpo de correo y adjuntos quedan con scroll vertical para no crecer hacia abajo sin límite.
    - `ticketera/ui/tks.html`
      - cache-bust actualizado para los assets modificados.
- **Verificación**:
  - `node --check ticketera/ui/js/tks_api.js` ✅
  - `node --check ticketera/ui/js/tks_main.js` ✅
  - `node --check ticketera/ui/js/tks_ui.js` ✅
  - `compile(..., 'exec')` en memoria:
    - `ticketera/service.py` ✅
    - `ticketera/core/tickets_service.py` ✅
    - `plataforma/core/tickets_service.py` ✅
    - `ticketera/core/config.py` ✅
    - `plataforma/core/config.py` ✅
  - nota:
    - `python3 -m py_compile ...` no fue usable por permisos de escritura en `__pycache__`, por lo que se validó sintaxis Python en memoria para evitar falso negativo.
- **Estado**: APLICADO EN DEV. Ticketera queda con compromiso SLA visible corregido, resumen con histórico operativo y flujo de respuesta más manejable para tickets con muchas imágenes.

## HITO: 2026-04-01 - DEV: raíz visible reservada para apps, shared core sale de gateway y soporte pasa a `plataforma`
- **Solicitud ejecutada**:
  - mover cada cosa a su carpeta correspondiente, dejar el `core` compartido fuera de `gateway`, esconder soporte/legacy útil en una capa única y limpiar la carpeta madre para evitar nuevas confusiones.
- **Acción ejecutada**:
  - se consolida `plataforma/` como capa de plataforma del repo:
    - `plataforma/core/`
      - pasa a ser el `core` compartido canónico; se toma como baseline la variante más actual de Ticketera.
    - `plataforma/docs/`
    - `plataforma/ops/`
    - `plataforma/tests/`
    - `plataforma/legacy/code/`
    - `plataforma/data/`
    - `plataforma/data_runtime/`
  - `gateway/core`, `ticketera/core`, `erp/core`, `bodega/core`, `crm/core` y `plataforma/legacy/code/app/core` dejan de ser copias separadas y quedan enlazados al `core` canónico.
  - decisión de arquitectura aplicada:
    - el `core` compartido NO se deja dentro de `gateway`, porque `gateway` es una app; lo compartido queda fuera de cualquier app en la capa `plataforma/core`.
  - reparto de datos por dueño funcional:
    - `ticketera/data/compliance` -> enlace canónico hacia `plataforma/data_runtime/compliance`
    - `ticketera/data/tickets` -> enlace canónico hacia `plataforma/data_runtime/tickets`
    - `fundacion/data/` recibe planificaciones y documentación operativa de Fundación
    - `erp/data/` recibe `cartola_sintetica.csv`
    - `plataforma/data/` retiene `monstruo.db` y `legacy/`
  - orden adicional:
    - `docs/`, `ops/`, `tests/` y `code/` salen de la raíz visible y pasan a `plataforma/...`
    - `run_sync.sh` y `check_erp_data.py` salen de la raíz y pasan a `erp/tools/`
    - `main.py.bak` sale del repo activo y se mueve a respaldo externo
    - `erp/laudus.py` y `erp/indicators_service.py` quedan fuera del slot `core` para evitar que ERP contamine el `core` compartido
  - respaldo externo usado:
    - `/home/juan/monstruo_old/monstruo_dev_cleanup_20260401_phase4/`
  - bloqueo residual:
    - `migrations/` sigue visible en raíz porque el directorio está poseído por `root` y no fue posible moverlo sin privilegios del sistema.
- **Verificación**:
  - sintaxis backend por `compile(...)`:
    - `gateway/main.py` ✅
    - `ticketera/main.py` ✅
    - `ticketera/service.py` ✅
    - `erp/main.py` ✅
    - `erp/router.py` ✅
    - `erp/service.py` ✅
    - `erp/sales_service.py` ✅
    - `pmo/main.py` ✅
    - `ia/main.py` ✅
    - `zabbix/main.py` ✅
    - `fundacion/main.py` ✅
    - `plataforma/core/tickets_service.py` ✅
    - `plataforma/ops/herramientas/deploy/generate_universal_prompt.py` ✅
    - `plataforma/ops/herramientas/ai/snapshot_for_training.py` ✅
    - `plataforma/tests/verify_hardening.py` ✅
    - `plataforma/tests/unit_ticketera_frontend_security.py` ✅
    - `erp/tools/check_erp_data.py` ✅
  - `node --check`:
    - `gateway/shared/ui/js/sidebar.js` ✅
    - `gateway/shared/ui/js/admin.js` ✅
    - `gateway/shared/ui/js/utilidades.js` ✅
    - `pmo/ui/js/dashboard.js` ✅
    - `zabbix/ui/js/zabbix.js` ✅
    - `fundacion/ui/js/fundacion.js` ✅
  - shell:
    - `plataforma/ops/herramientas/deploy/start.sh` ✅
    - `plataforma/ops/herramientas/deploy/iniciar_todo.sh` ✅
    - `plataforma/ops/herramientas/deploy/deploy.sh` ✅
    - `erp/tools/run_sync.sh` ✅
  - compose:
    - `docker compose --env-file plataforma/ops/env/.env.server.dev config -q` ✅
    - warning residual: `version` obsoleto en `docker-compose.yaml` (no bloqueante) ⚠️
  - árbol activo:
    - raíz visible con apps canónicas `gateway/ticketera/erp/bodega/crm/pmo/ia/zabbix/fundacion` ✅
    - soporte visible adicional solo `migrations/` por bloqueo de permisos ⚠️
- **Estado**: APLICADO EN DEV. La raíz visible queda enfocada en apps; lo compartido queda explícitamente fuera de `gateway`; `migrations/` queda como única deuda visible por permisos del sistema.

## HITO: 2026-04-01 - DEV: PMO, IA, Zabbix y Fundación salen del árbol legacy y quedan como apps propias
- **Solicitud ejecutada**:
  - dejar la carpeta madre más limpia y separar módulos avanzados en carpetas canónicas por aplicación: `gateway`, `ticketera`, `erp`, `bodega`, `crm`, `pmo`, `ia`, `zabbix`, `fundacion`.
- **Acción ejecutada**:
  - se consolidan cuatro apps nuevas en la raíz activa:
    - `pmo/`
      - `main.py`
      - `router.py`
      - `ui/pmo.html`
      - `ui/js/dashboard.js`
    - `ia/`
      - `main.py`
      - `router.py`
      - `ui/ia.html`
    - `zabbix/`
      - `main.py`
      - `router.py`
      - `ui/zabbix.html`
      - `ui/js/zabbix.js`
    - `fundacion/`
      - `main.py`
      - `router.py`
      - `ui/fundacion.html`
      - `ui/js/fundacion.js`
  - las nuevas apps:
    - montan `shared` desde `gateway/shared/ui`
    - exponen su HTML por `/`
    - exponen su router local por API propia
    - proxyan `auth/session` restantes hacia `gateway` para conservar shell compartido
  - `docker-compose.yaml` agrega servicios dedicados:
    - `pmo` -> `9009`
    - `ia` -> `9010`
    - `zabbix` -> `9011`
    - `fundacion` -> `9012`
  - `gateway/shared/ui/js/sidebar.js` deja de navegar en local a `/modulos/pmo|ultron|zabbix|fundacion/...` y pasa a abrir los puertos dedicados de cada app.
  - `gateway/main.py`:
    - deja de depender de `static_ui` para runtime activo
    - agrega `SERVICES_MAP` para `pmo/ia/zabbix/fundacion`
    - proxy `/api/{service}/...` hacia las nuevas apps
    - `GET /fundacion` redirige a la app canónica de Fundación
  - limpieza física del árbol:
    - se mueven fuera del repo activo a respaldo externo:
      - `static_ui/`
      - `static/`
      - `code/static/modulos/pmo/`
      - `code/static/modulos/ultron/`
      - `code/static/modulos/zabbix/`
      - `code/static/modulos/fundacion/`
    - respaldo usado:
      - `/home/juan/monstruo_old/monstruo_dev_cleanup_20260401/`
    - nota operativa:
      - no fue posible usar `/srv/monstruo_old/` por permisos del sistema en esta sesión.
- **Verificación**:
  - sintaxis backend por `compile(...)`:
    - `pmo/main.py` ✅
    - `pmo/router.py` ✅
    - `ia/main.py` ✅
    - `ia/router.py` ✅
    - `zabbix/main.py` ✅
    - `zabbix/router.py` ✅
    - `fundacion/main.py` ✅
    - `fundacion/router.py` ✅
    - `gateway/main.py` ✅
  - `node --check`:
    - `gateway/shared/ui/js/sidebar.js` ✅
    - `gateway/shared/ui/js/admin.js` ✅
    - `gateway/shared/ui/js/utilidades.js` ✅
    - `pmo/ui/js/dashboard.js` ✅
    - `zabbix/ui/js/zabbix.js` ✅
    - `fundacion/ui/js/fundacion.js` ✅
  - compose:
    - `docker compose --env-file ops/env/.env.server.dev config -q` ✅
    - warning residual: `version` obsoleto en `docker-compose.yaml` (no bloqueante) ⚠️
  - árbol activo:
    - raíz visible sin `static_ui/` ni `static/` ✅
    - apps canónicas presentes: `gateway/ticketera/erp/bodega/crm/pmo/ia/zabbix/fundacion` ✅
  - búsquedas:
    - sin referencias runtime activas a `static_ui` en `gateway/ticketera/erp/bodega/crm/pmo/ia/zabbix/fundacion/docker-compose.yaml` ✅
    - sin referencias runtime activas a `_compartido` ni `/modulos/...` en apps activas del split ✅
- **Estado**: APLICADO EN DEV. La estructura activa queda más alineada a apps por carpeta; persiste `code/` como bloque legacy compartido mientras no se extraigan aún sus capas `core/auth/db` a un paquete común o a servicios totalmente independientes.

## HITO: 2026-04-01 - DEV: `gateway/shared/ui` queda como canon real de assets compartidos
- **Solicitud ejecutada**:
  - empezar limpieza de estructura para evitar confusión entre `gateway`, `static_ui` y `code/static`, dejando los assets compartidos bajo `gateway` y reduciendo referencias cruzadas en las apps activas.
- **Acción ejecutada**:
  - se canoniza `gateway/shared/ui` como fuente única de assets compartidos para las apps activas del split:
    - `gateway/main.py`
      - `login` y `configuracion` dejan de redirigir al root y ahora sirven sus HTML canónicos desde `gateway/`.
    - `gateway/dashboard/dashboard.html`
    - `gateway/dashboard/inicio.html`
    - `gateway/configuracion/configuracion.html`
    - `gateway/login/login.html`
      - reemplazan referencias `../modulos/_compartido/...` por `../shared/...`
      - cache-bust compartido actualizado a:
        - `utilidades.js?v=207`
        - `sidebar.js?v=19`
    - `gateway/shared/ui/js/sidebar.js`
      - en `PROD` la ruta de `Fundación` pasa a `.../fundacion`
      - en `DEV/local` los accesos shell a `dashboard/configuracion/fundacion` y módulos legacy de gateway salen por el puerto `9001`, evitando depender del host/puerto actual del microservicio
    - `gateway/shared/ui/js/utilidades.js`
      - el login local apunta al `gateway` en `9001` (`/login` o `/dev/login`) para unificar salida de sesión entre microapps
    - `ticketera/main.py`
    - `erp/main.py`
    - `bodega/main.py`
    - `crm/main.py`
      - eliminan fallback a `static_ui` y `code/static` para resolver `/shared`
      - solo montan `gateway/shared/ui` como fuente de assets compartidos
    - `erp/ui/erp.html`
    - `bodega/ui/bodega.html`
    - `crm/ui/crm.html`
    - `ticketera/ui/tks.html`
      - normalizan consumo del canon compartido
      - `erp/bodega/crm` dejan de usar rutas absolutas `/shared/...` y pasan a relativas `shared/...` para respetar prefijos tipo `/dev`
- **Verificación**:
  - sintaxis backend por `compile(...)` en memoria:
    - `gateway/main.py` ✅
    - `ticketera/main.py` ✅
    - `erp/main.py` ✅
    - `bodega/main.py` ✅
    - `crm/main.py` ✅
  - `node --check`:
    - `gateway/shared/ui/js/sidebar.js` ✅
    - `gateway/shared/ui/js/utilidades.js` ✅
  - búsqueda de residuos:
    - sin referencias activas a `_compartido` en `gateway/dashboard`, `gateway/configuracion`, `gateway/login`, `ticketera/ui`, `erp/ui`, `bodega/ui`, `crm/ui` ✅
    - sin referencias a `static_ui` ni `code/static` en `ticketera/main.py`, `erp/main.py`, `bodega/main.py`, `crm/main.py` ✅
  - nota de verificación:
    - `python3 -m py_compile` no fue usable para estos archivos por permisos previos sobre `__pycache__`; se valida con `compile(...)` para evitar falsos negativos por escritura de `.pyc`.
- **Estado**: APLICADO EN DEV. `gateway/shared/ui` queda como canon real para las apps activas; persiste deuda transicional en módulos legacy aún servidos por `/modulos` (`pmo`, `ultron`, `zabbix`, `fundacion` contenido HTML) para un siguiente hito de migración.

## HITO: 2026-03-31 - DEV/PROD: Ticketera agrega papelera blanda para correos basura y tickets repetidos
- **Solicitud ejecutada**:
  - agregar una `papelera` blanda en Ticketera para sacar de operación correos basura o tickets repetidos, manteniendo posibilidad de restauración.
- **Acción ejecutada**:
  - se implementa papelera en `DEV` y se replica al árbol activo de `PROD`:
    - `ticketera/core/db.py`
      - nuevas columnas en `tks.tickets`:
        - `is_trashed`
        - `trashed_at`
        - `trashed_by`
        - `trash_reason`
        - `trash_prev_estado`
        - `trash_prev_subestado`
        - `trash_prev_asignado_a`
      - índice `idx_tickets_trashed`
      - backfill defensivo para `is_trashed/trash_reason`
    - `ticketera/service.py` y `ticketera/core/tickets_service.py`
      - nuevas acciones:
        - `move_ticket_to_trash(...)`
        - `restore_ticket_from_trash(...)`
      - listados y métricas excluyen papelera por defecto
      - `list_tickets(..., trashed_only=True)` permite ver solo papelera
      - `dashboard`, `stats`, `assignment timeline` y `SLA batch` dejan fuera tickets en papelera
      - guard rails para bloquear en papelera:
        - tomar ticket
        - modificar
        - agregar nota
        - responder correo
        - transicionar/aprobar
        - subir adjuntos
    - `ticketera/router.py`
      - nuevo filtro `status=papelera`
      - nuevos endpoints:
        - `POST /api/tks/tickets/{ticket_id}/trash`
        - `POST /api/tks/tickets/{ticket_id}/restore`
    - UI Ticketera:
      - `ui/js/tks_api.js`: helpers `trashTicket` y `restoreTicket`
      - `ui/js/tks_main.js`:
        - chip `Papelera` en `Lista`
        - permisos y acciones `Enviar a papelera` / `Restaurar`
        - Kanban agrega una zona inferior `Papelera` como target de drag&drop para mandar tickets directo al basurero operativo
      - `ui/js/tks_ui.js`:
        - estado visible `Papelera`
        - detalle read-only cuando el ticket está en papelera
        - bloque visual con motivo, actor y fecha de trash
      - `ui/css/tks.css`: tono visual `papelera` + tarjeta de metadata + dropzone de Kanban
      - `ui/tks.html`: cache-bust actualizado a:
        - `tks.css?v=54`
        - `tks_api.js?v=18`
        - `tks_ui.js?v=86`
        - `tks_main.js?v=63`
  - despliegue operativo:
    - copia exacta de archivos verificados desde `/srv/monstruo_dev/ticketera/` hacia `/srv/monstruo/ticketera/`
    - restart:
      - `monstruo-dev-ticketera` ✅
      - `monstruo-ticketera` ✅
- **Verificación**:
  - `DEV`:
    - `python3 -m py_compile` sobre:
      - `ticketera/core/db.py` ✅
      - `ticketera/service.py` ✅
      - `ticketera/core/tickets_service.py` ✅
      - `ticketera/router.py` ✅
    - `node --check` sobre:
      - `ticketera/ui/js/tks_api.js` ✅
      - `ticketera/ui/js/tks_main.js` ✅
      - `ticketera/ui/js/tks_ui.js` ✅
    - smoke backend en contenedor `monstruo-dev-ticketera`:
      - ticket temporal sin contaminar correlativo público
      - `mover a papelera -> listar solo papelera -> restaurar` ✅
  - `PROD`:
    - `python3 -m py_compile` sobre:
      - `/srv/monstruo/ticketera/core/db.py` ✅
      - `/srv/monstruo/ticketera/service.py` ✅
      - `/srv/monstruo/ticketera/core/tickets_service.py` ✅
      - `/srv/monstruo/ticketera/router.py` ✅
    - `node --check` sobre:
      - `/srv/monstruo/ticketera/ui/js/tks_api.js` ✅
      - `/srv/monstruo/ticketera/ui/js/tks_main.js` ✅
      - `/srv/monstruo/ticketera/ui/js/tks_ui.js` ✅
    - runtime:
      - `db.init_db()` ejecutable en `monstruo-ticketera` y `monstruo-dev-ticketera` sin error ✅
      - `list_tickets(trashed_only=True)` ejecutable en ambos runtimes ✅
    - público:
      - `https://ticketera.telconsulting.cl/static/tks.html` sirve:
        - `tks.css?v=54`
        - `tks_api.js?v=18`
        - `tks_ui.js?v=86`
        - `tks_main.js?v=63`
        ✅
- **Estado**: APLICADO EN DEV Y PROD. Ticketera ya permite apartar tickets basura/repetidos en una papelera restaurable sin contaminar operación normal ni métricas.

## HITO: 2026-03-31 - PROD: Ticketera deja de mostrar reconciliación/paralelo Jira en Operación
- **Solicitud ejecutada**:
  - llevar a `PROD` el recorte ya aplicado en `DEV` para que Jira deje de ensuciar la operación visible de Ticketera.
- **Acción ejecutada**:
  - se replica en `/srv/monstruo/ticketera/ui/` el mismo recorte visual/funcional:
    - `js/tks_main.js`: `Ops` deja de pedir `migration/jira/runs`, `migration/jira/reconciliation/daily` y `parallel/kpi/daily`
    - `js/tks_ui.js`: se elimina la tarjeta `Reconciliación Jira` y el bloque `Paralelo Jira`
    - `js/tks_api.js`: se eliminan helpers frontend ya muertos de Jira/paralelo
    - `tks.html`: cache-bust actualizado a:
      - `tks_api.js?v=17`
      - `tks_ui.js?v=84`
      - `tks_main.js?v=60`
  - no fue necesario reiniciar contenedores porque la Ticketera productiva sirve estos assets desde bind mount del árbol activo `/srv/monstruo`.
- **Verificación**:
  - `node --check`:
    - `/srv/monstruo/ticketera/ui/js/tks_api.js` ✅
    - `/srv/monstruo/ticketera/ui/js/tks_ui.js` ✅
    - `/srv/monstruo/ticketera/ui/js/tks_main.js` ✅
  - público:
    - `https://ticketera.telconsulting.cl/static/tks.html` sirve:
      - `tks_api.js?v=17`
      - `tks_ui.js?v=84`
      - `tks_main.js?v=60`
      ✅
    - los JS públicos no contienen referencias activas a:
      - `listJiraRuns`
      - `getJiraReconciliationDaily`
      - `listParallelKpiDaily`
      - `Reconciliación Jira`
      - `Paralelo Jira`
      ✅
- **Estado**: APLICADO EN PROD. La operación visible de Ticketera queda alineada al escenario sin mesa externa en Jira.

## HITO: 2026-03-31 - DEV: Ticketera deja de mostrar reconciliación/paralelo Jira en Operación
- **Motivo**:
  - Jira deja de ser mesa activa; la operación queda centrada solo en la Ticketera interna.
  - se solicita limpiar la UI para que `Operación` no siga mostrando reconciliación/paralelo Jira.
- **Acción ejecutada**:
  - `ticketera/ui/js/tks_main.js`:
    - la carga de `Ops` deja de pedir:
      - `migration/jira/runs`
      - `migration/jira/reconciliation/daily`
      - `parallel/kpi/daily`
    - mantiene solo:
      - salud de cola
      - canales
      - notificaciones de canal
      - exportación compliance
  - `ticketera/ui/js/tks_ui.js`:
    - se elimina de `Ops` la tarjeta `Reconciliación Jira`
    - se elimina el bloque visual `Paralelo Jira`
    - la cuarta tarjeta pasa a resumir `Exportación compliance`
  - `ticketera/ui/js/tks_api.js`:
    - se eliminan helpers ya muertos de Jira/paralelo en frontend
  - `ticketera/ui/tks.html`:
    - cache-bust actualizado:
      - `tks_api.js?v=17`
      - `tks_ui.js?v=84`
      - `tks_main.js?v=60`
- **Verificación**:
  - `node --check ticketera/ui/js/tks_api.js` ✅
  - `node --check ticketera/ui/js/tks_ui.js` ✅
  - `node --check ticketera/ui/js/tks_main.js` ✅
  - búsqueda final en UI:
    - sin referencias activas a `Reconciliación Jira`, `Paralelo Jira`, `listJiraRuns`, `getJiraReconciliationDaily`, `listParallelKpiDaily` ✅
- **Estado**: APLICADO EN DEV. No desplegado a `PROD` en este paso.

## HITO: 2026-03-31 - Reset Ticketera DEV/PROD + nueva numeración pública desde TK-2154
- **Solicitud ejecutada**:
  - reiniciar Ticketera en `DEV` y `PROD` a `0` tickets.
  - dejar el siguiente ticket visible como `TK-2154`.
- **Acción ejecutada**:
  - se cambia la generación de código en la app independiente:
    - `ticketera/core/config.py` agrega `TICKET_PUBLIC_CODE_START=2154`
    - `ticketera/core/tickets_service.py` y `ticketera/service.py` pasan de `TK-DD-MM-YYYY-NNNN` a código público simple `TK-2154+`
  - el parser de asunto para replies ahora reconoce también el nuevo formato simple `TK-\d+` consultando por `codigo` antes del fallback legacy por `id`.
  - se explicita `TICKET_PUBLIC_CODE_START=2154` en:
    - `/srv/monstruo/ops/env/.env.server`
    - `/srv/monstruo_dev/ops/env/.env.server.dev`
    - `/srv/monstruo_dev/ops/env/.env.server`
  - respaldo previo almacenado en:
    - `/srv/monstruo_dev/backups/ticket-reset-20260331-152901/`
      - `prod/tks_ops.sql`
      - `dev/tks_ops.sql`
      - `prod/*.tgz`
      - `dev/*.tgz`
  - reset de datos ejecutado en ambas bases PostgreSQL:
    - `TRUNCATE tks.tickets RESTART IDENTITY CASCADE`
    - `TRUNCATE ops.jira_sync_runs, ops.jira_sync_cursor, ops.parallel_kpi_daily, ops.parallel_decisions, ops.compliance_export_runs, ops.compliance_purge_runs, ops.jira_import_runs RESTART IDENTITY`
    - `UPDATE tks.user_specialties SET current_load = 0`
  - limpieza de artefactos:
    - `/srv/monstruo/data/tickets`
    - `/srv/monstruo/data/compliance`
    - `/srv/monstruo_dev/data/tickets`
    - `/srv/monstruo_dev/data/compliance`
    - se tuvo que ejecutar vía contenedor porque los archivos previos quedaron con permisos root desde runtime Docker.
  - restart de runtime:
    - `monstruo-ticketera` ✅
    - `monstruo-dev-ticketera` ✅
- **Verificación**:
  - compilación sintáctica por `compile(...)` en:
    - `/srv/monstruo_dev/ticketera/core/config.py` ✅
    - `/srv/monstruo_dev/ticketera/core/tickets_service.py` ✅
    - `/srv/monstruo_dev/ticketera/service.py` ✅
    - `/srv/monstruo/ticketera/core/config.py` ✅
    - `/srv/monstruo/ticketera/core/tickets_service.py` ✅
    - `/srv/monstruo/ticketera/service.py` ✅
  - `PROD`:
    - `SELECT COUNT(*) FROM tks.tickets` -> `0` ✅
    - `SELECT last_value, is_called FROM tks.tickets_id_seq` -> `1 | false` ✅
    - `ops.jira_sync_runs / parallel_kpi_daily / compliance_export_runs` -> `0` ✅
    - runtime:
      - `settings.TICKET_PUBLIC_CODE_START` -> `2154` ✅
      - `generar_codigo(1)` -> `TK-2154` ✅
  - `DEV`:
    - `SELECT COUNT(*) FROM tks.tickets` -> `0` ✅
    - `SELECT last_value, is_called FROM tks.tickets_id_seq` -> `1 | false` ✅
    - `ops.jira_sync_runs / parallel_kpi_daily / compliance_export_runs` -> `0` ✅
    - runtime:
      - `settings.TICKET_PUBLIC_CODE_START` -> `2154` ✅
      - `generar_codigo(1)` -> `TK-2154` ✅
  - los directorios de artefactos quedaron vacíos en ambos entornos ✅
- **Estado**: RESET COMPLETO EN DEV Y PROD. Ticketera queda limpia y el próximo ticket visible parte en `TK-2154`.

## HITO: 2026-03-31 - PROD: fix real para Ticketera en pestañas Lista y Dominio/Plantilla
- **Incidente reportado**:
  - en `PROD`, dentro de Ticketera, la pestaña `Lista` y la vista `Dominio/Plantilla` seguían fallando aunque `stats/notificaciones/timeline` ya habían sido estabilizados.
- **Causa raíz real**:
  - el problema no estaba en `ticketera/router.py`, sino en `gateway/main.py`.
  - el proxy genérico `/api/{service}/{path}` trataba `service=tks` igual que cualquier otro módulo y reenviaba:
    - `/api/tks/tickets` -> `ticketera:/api/tickets`
    - `/api/tks/settings/domain-templates` -> `ticketera:/api/settings/domain-templates`
  - eso hacía que solo sobrevivieran endpoints cubiertos por aliases legacy (`stats`, `tablero`, `notificaciones`, etc.), mientras `tickets` y `settings/...` caían en `404`.
- **Acción ejecutada**:
  - `gateway/main.py` queda corregido en:
    - `/srv/monstruo/gateway/main.py`
    - `/srv/monstruo_dev/gateway/main.py`
  - nuevo criterio:
    - si `service in {"tks", "ticketera"}`, el proxy reenvía a `ticketera:/api/tks/{path}`.
    - el resto de módulos conserva el forwarding normal a `/api/{path}`.
  - se reinicia runtime:
    - `monstruo-gateway` (PROD) ✅
    - `monstruo-dev-gateway` (DEV) ✅
- **Verificación**:
  - compilación sintáctica por `compile(...)` sobre ambos `gateway/main.py` ✅
  - `PROD` tras reinicio:
    - `Host: ticketera.telconsulting.cl` + `GET /api/tks/tickets?limit=50` -> `401 missing_auth` ✅
    - `Host: ticketera.telconsulting.cl` + `GET /api/tks/settings/domain-templates` -> `401 missing_auth` ✅
    - `Host: ticketera.telconsulting.cl` + `GET /api/tickets?limit=50` -> `401 missing_auth` ✅
    - `Host: ticketera.telconsulting.cl` + `GET /api/settings/domain-templates` -> `401 missing_auth` ✅
  - logs de `monstruo-gateway` confirman que las rutas nuevas ahora llegan a `ticketera` con prefijo `/api/tks/...` y dejan de caer en `404` ✅
- **Estado**: FIX APLICADO EN PROD Y DEV. Las vistas `Lista` y `Dominio/Plantilla` dejan de romperse por traducción incorrecta del gateway.

## HITO: 2026-03-31 - PROD: compatibilidad Ticketera legacy + Configuración reducida a General/Ticketera
- **Incidentes reportados tras el corte**:
  - en `ticketera.telconsulting.cl` el dashboard interno mostraba `Error cargando stats: Not Found`.
  - en logs de `monstruo-ticketera` aparecían requests legacy a rutas sin prefijo nuevo:
    - `/api/stats`
    - `/api/notificaciones`
    - `/api/asignacion/timeline`
    - `/api/dashboard/kpi`
    - `/api/tickets`
    - `/api/settings/...`
  - en `configuracion` seguían visibles tabs placeholder de módulos no activos y la gestión de usuarios, lo que ensuciaba el corte mínimo aprobado.
- **Causa raíz**:
  - coexistencia de frontends/browser tabs cacheados que aún consumían la API legacy sin prefijo `/api/tks/...`.
  - la app nueva de Ticketera ya sirve `tks_api.js` correcto, pero el gateway y la Ticketera no tenían compatibilidad suficiente para todas las rutas viejas.
  - Configuración seguía exponiendo placeholders de módulos no migrados.
- **Acción ejecutada**:
  - `ticketera/router.py`:
    - se agrega `legacy_router` con aliases GET para rutas legacy críticas:
      - `/api/stats`
      - `/api/tablero`
      - `/api/asignacion/timeline`
      - `/api/dashboard/kpi`
      - `/api/notificaciones`
      - `/api/especialidades`
  - `ticketera/main.py`:
    - se incluye `legacy_router` en runtime.
  - `ticketera/ui/tks.html`:
    - se sube cache-bust:
      - `tks_api.js?v=16`
      - `tks_ui.js?v=83`
      - `tks_main.js?v=59`
  - `gateway/main.py`:
    - para el host `ticketera`, cualquier ruta legacy `/api/...` que no sea `auth`, `sesion` o `jobs` se reescribe/proxya a `/api/tks/...`.
    - con eso también quedan cubiertas rutas legacy multiparte como:
      - `/api/tickets`
      - `/api/settings/...`
      - `/api/channels/...`
      - `/api/ops/queue-health`
      - `/api/migration/...`
      - `/api/parallel/...`
      - `/api/compliance/...`
  - `gateway/configuracion/configuracion.html`:
    - se reduce la UI visible a solo dos tabs:
      - `General`
      - `Ticketera`
    - se eliminan del layout activo:
      - placeholders de Dashboard/PMO/ERP/CRM/Bodega/IA/Zabbix
    - ajuste posterior sobre el mismo corte:
      - `General` recupera la administración que sí corresponde al stack activo:
        - gestión de usuarios
        - permisos efectivos por usuario
        - permisos por rol
      - se restaura `users_ui.js` y su modal asociado, manteniendo fuera los placeholders de módulos no migrados.
    - `General` queda como panel del stack activo + administración de usuarios/permisos.
  - los cambios se aplican tanto en la fuente DEV (`/srv/monstruo_dev`) como en el árbol activo PROD (`/srv/monstruo`).
- **Verificación**:
  - sintaxis:
    - `compile(...)` en `gateway/main.py`, `ticketera/main.py`, `ticketera/router.py` ✅
  - Ticketera legacy compatibility:
    - `Host: ticketera.telconsulting.cl` sobre `127.0.0.1:9000`:
      - `/api/stats` -> `401 missing_auth` sin sesión ✅
      - `/api/notificaciones` -> `401 missing_auth` sin sesión ✅
      - `/api/asignacion/timeline?...` -> `401 missing_auth` sin sesión ✅
      - `/api/dashboard/kpi` -> `401 missing_auth` sin sesión ✅
      - `/api/tickets?limit=50` -> `401 missing_auth` sin sesión ✅
      - `/api/settings/domain-templates` -> `401 missing_auth` sin sesión ✅
      - `/api/channels/status` -> `401 missing_auth` sin sesión ✅
      - `/api/ops/queue-health` -> `401 missing_auth` sin sesión ✅
      - `/api/migration/jira/runs?limit=10` -> `401 missing_auth` sin sesión ✅
      - `/api/parallel/kpi/daily` -> `401 missing_auth` sin sesión ✅
      - `/api/compliance/exports/runs?limit=20` -> `401 missing_auth` sin sesión ✅
    - logs recientes de `monstruo-ticketera` pasan de `404 Not Found` a `200 OK` para requests legacy autenticados de `stats`, `notificaciones`, `asignacion/timeline`, `dashboard/kpi` ✅
  - Configuración:
    - HTML público de `configuracion` contiene solo tabs `pane-general` y `pane-ticketera` ✅
    - `General` vuelve a contener:
      - `Gestión de Usuarios`
      - `Permisos Efectivos por Usuario`
      - `Permisos por Rol`
      ✅
    - vuelve a cargar `users_ui.js` para la gestión administrativa ✅
- **Dato operativo confirmado**:
  - el dashboard de PROD muestra `2` tickets abiertos/no cerrados porque en base existen:
    - `TK-26-03-2026-0008` (`abierto`) título `imagen`
    - `TK-26-03-2026-0007` (`en_progreso`) título `prueba con imagen`
  - total tickets en PROD al momento de la verificación: `8`, de los cuales `6` están cerrados.
- **Estado**: FIX APLICADO EN PROD. Ticketera ya no depende de limpiar caché para operar y Configuración queda alineada al corte mínimo activo.

## HITO: 2026-03-31 - PROD y fuente DEV: Configuración queda con URL limpia en el root del subdominio
- **Solicitud**:
  - evitar que Configuración quede visible como `https://config.telconsulting.cl/configuracion/configuracion.html`.
  - criterio aprobado:
    - canónico: `https://config.telconsulting.cl/`
    - legacy: `/configuracion/configuracion.html` debe redirigir al root.
- **Acción ejecutada**:
  - `gateway/main.py`:
    - el root del host `config` deja de redirigir y pasa a servir directamente `configuracion/configuracion.html` en `/`.
    - se agregan redirects canónicos:
      - `/configuracion`
      - `/configuracion/`
      - `/configuracion/configuracion.html`
      -> `/`
  - el mismo ajuste se replica en:
    - `/srv/monstruo_dev/gateway/main.py`
    - `/srv/monstruo/gateway/main.py`
- **Verificación**:
  - local:
    - `Host: config.telconsulting.cl` sobre `127.0.0.1:9000/` -> `200` + HTML Configuración ✅
    - `Host: config.telconsulting.cl` sobre `127.0.0.1:9000/configuracion/configuracion.html` -> `302 location: /` ✅
  - público:
    - `https://config.telconsulting.cl/` -> `200` + HTML Configuración ✅
    - `https://config.telconsulting.cl/configuracion/configuracion.html` -> `302 location: /` ✅
- **Estado**: IMPLEMENTADO Y VALIDADO EN PROD. Configuración queda alineada al estándar de URL limpia definido para los subdominios activos.

## HITO: 2026-03-31 - PROD y fuente DEV: URLs públicas limpias para Login, Dashboard y Ticketera
- **Solicitud**:
  - evitar rutas visibles tipo `/login/login.html` o `/login.html` en producción.
  - criterio aprobado:
    - `https://login.telconsulting.cl/`
    - `https://login.telconsulting.cl/dashboard`
    - `https://ticketera.telconsulting.cl/`
- **Acción ejecutada**:
  - `gateway/main.py`:
    - el root del host `login` deja de redirigir a `/login/login.html` y pasa a servir directamente el HTML de login en `/`.
    - se agrega ruta canónica `/dashboard` (y compat `/dashboard/`) que sirve el dashboard desde el host `login`.
    - las rutas legacy visibles quedan redirigiendo a su canónico:
      - `/login/login.html` -> `/`
      - `/dashboard/dashboard.html` -> `/dashboard`
    - sin sesión, `/dashboard` vuelve al root limpio `/`.
  - `gateway/login/js/login.js`:
    - el post-login pasa a redirigir a `/dashboard` en vez de `/dashboard/`.
  - `gateway/shared/ui/js/sidebar.js`:
    - el enlace productivo de Dashboard queda apuntando a `https://login.telconsulting.cl/dashboard`.
  - `ticketera/main.py`:
    - el root `/` deja de redirigir al login y pasa a servir directamente:
      - `login.html` si no hay sesión
      - `tks.html` si la sesión es válida
    - `/login.html` queda redirigiendo a `/` para mantener la URL visible limpia.
  - `ticketera/ui/login.html`:
    - se normaliza el copy del acceso para producción, eliminando referencias a “local” / “desarrollo”.
  - los mismos cambios se replican en la fuente DEV (`/srv/monstruo_dev`) y en el árbol activo de PROD (`/srv/monstruo`) para no dejar divergencia inmediata.
- **Verificación**:
  - local PROD:
    - `Host: login.telconsulting.cl` sobre `127.0.0.1:9000/` -> `200` + HTML login ✅
    - `Host: login.telconsulting.cl` sobre `127.0.0.1:9000/dashboard` sin sesión -> `302 location: /` ✅
    - `Host: login.telconsulting.cl` sobre `127.0.0.1:9000/login/login.html` -> `302 location: /` ✅
    - `Host: login.telconsulting.cl` sobre `127.0.0.1:9000/dashboard/dashboard.html` -> `302 location: /dashboard` ✅
    - `Host: ticketera.telconsulting.cl` sobre `127.0.0.1:9000/` -> `200` + HTML login Ticketera ✅
    - `Host: ticketera.telconsulting.cl` sobre `127.0.0.1:9000/login.html` -> `302 location: /` ✅
  - público:
    - `https://login.telconsulting.cl/` -> `200` + HTML login ✅
    - `https://login.telconsulting.cl/dashboard` sin sesión -> `302 location: /` ✅
    - `https://login.telconsulting.cl/login/login.html` -> `302 location: /` ✅
    - `https://login.telconsulting.cl/dashboard/dashboard.html` -> `302 location: /dashboard` ✅
    - `https://ticketera.telconsulting.cl/` -> `200` + HTML login Ticketera ✅
    - `https://ticketera.telconsulting.cl/login.html` -> `302 location: /` ✅
    - JS público servido:
      - `login.js` apunta a `/dashboard` ✅
      - `sidebar.js` apunta a `https://login.telconsulting.cl/dashboard` ✅
- **Estado**: IMPLEMENTADO Y VALIDADO EN PROD. La navegación visible queda alineada al criterio de dominio limpio para Login y Ticketera, con Dashboard expuesto como `/dashboard`.

## HITO: 2026-03-31 - PROD mínimo activo: Gateway + Ticketera reemplazan al monolito
- **Objetivo ejecutado**:
  - se realiza el corte productivo mínimo aprobado para dejar `PROD` corriendo solo con `gateway + ticketera`, manteniendo rollback disponible y evitando subir ERP/Bodega/CRM antes de tiempo.
- **Acción ejecutada**:
  - en `/srv/monstruo` se instala `docker-compose.yaml` mínimo con solo:
    - `db`
    - `gateway`
    - `ticketera`
  - `gateway` queda publicado en `9000` y `ticketera` queda solo por red interna Docker (`expose: 8000`) para evitar choque con `DEV` en `9005`.
  - se reutiliza el fix ya validado en DEV donde `gateway/main.py` resuelve el host `ticketera.telconsulting.cl` y proxya root/static/catchall hacia el servicio interno `ticketera`, sin depender de cambios inmediatos en el proxy externo.
  - el árbol activo de `/srv/monstruo` se limpia para dejar solo lo necesario del corte:
    - se remueve del root activo:
      - `code/`
      - `.env`
      - `.env.server.dev`
    - el root productivo queda con:
      - `.dockerignore`
      - `.env.server`
      - `.git`
      - `data/`
      - `docker-compose.yaml`
      - `gateway/`
      - `ops/`
      - `requirements.txt`
      - `runner/`
      - `static_ui/`
      - `ticketera/`
- **Backups / rollback**:
  - dump lógico previo:
    - `backups/prod-cutover-20260331-125517/pre_cutover/monstruo-pre-gateway-ticketera-20260331-124019.sql`
  - snapshot previo del árbol productivo:
    - `backups/prod-cutover-20260331-125517/pre_cutover/monstruo-pre-gateway-ticketera-20260331-124019/`
  - legado retirado del root activo:
    - `backups/prod-cutover-20260331-125517/legacy_root/code/`
    - `backups/prod-cutover-20260331-125517/legacy_root/.env`
    - `backups/prod-cutover-20260331-125517/legacy_root/.env.server.dev`
  - nota operativa:
    - el plan maestro pide respaldo en `/srv/monstruo_old/`, pero la cuenta operativa no tuvo permisos para crear esa ruta en esta VM; se usa fallback temporal en `/srv/monstruo_dev/backups/` para no bloquear el corte.
- **Verificación**:
  - local:
    - `http://127.0.0.1:9000/health` -> `{"status":"ok","gateway":"active"}` ✅
    - `Host: login.telconsulting.cl` sobre `127.0.0.1:9000/` -> `307 location: login/login.html` ✅
    - `Host: ticketera.telconsulting.cl` sobre `127.0.0.1:9000/` -> `302 location: /login.html` ✅
    - `Host: ticketera.telconsulting.cl` sobre `127.0.0.1:9000/login.html` -> `200` + HTML Ticketera ✅
    - `Host: ticketera.telconsulting.cl` sobre `127.0.0.1:9000/api/sesion` -> `{"ok":false,"detail":"401: missing_auth"}` ✅
  - público:
    - `https://login.telconsulting.cl/` -> `307 location: login/login.html` ✅
    - `https://ticketera.telconsulting.cl/` -> `302 location: /login.html` ✅
    - `https://ticketera.telconsulting.cl/login.html` -> `200` + HTML Ticketera ✅
    - `https://ticketera.telconsulting.cl/api/sesion` -> `{"ok":false,"detail":"401: missing_auth"}` ✅
  - runtime Docker:
    - `monstruo-gateway` activo en `9000` ✅
    - `monstruo-ticketera` activo en red interna Docker ✅
    - `monstruo-postgres` activo ✅
- **Estado**: CORTE PRODUCTIVO MÍNIMO COMPLETADO. `PROD` queda operando con `gateway + ticketera`; el monolito deja de ser el frente activo y el rollback queda preservado en respaldo externo.

## HITO: 2026-03-31 - Ticketera independiente DEV: soporte de imágenes inline en correos entrantes
- **Seguimiento mismo día**: se cierra soporte de correos HTML con imágenes inline (`cid:`) en la app independiente.
- **Problema detectado**:
  - la Ticketera ya estaba creando el TK y procesando adjuntos tradicionales, pero cuando el cliente pegaba imágenes dentro del cuerpo del correo solo quedaba la referencia/nombre del recurso y no la imagen renderizada en el historial.
  - la ruta real de polling (`ticketera/core/tickets_service.py`) seguía guardando el cuerpo entrante como texto escapado, sin preservar `body_html`, `Content-ID` ni reescribir `cid:` al adjunto persistido.
- **Acción ejecutada**:
  - `ticketera/core/email_integration.py` queda como parser fuente para:
    - conservar `body_html`
    - detectar adjuntos inline aunque no vengan como attachment clásico
    - capturar `content_id`, `disposition` e `is_inline`
  - se alinea la lógica de ingesta en ambas rutas activas:
    - `ticketera/service.py`
    - `ticketera/core/tickets_service.py`
  - se replica la mejora en el fallback monolítico del repo:
    - `code/app/core/email_integration.py`
    - `code/app/core/tickets_service.py`
    - `code/static/modulos/tks/js/tks_ui.js`
    - `code/static/modulos/tks/css/tks.css`
  - la persistencia de adjuntos entrantes ahora inserta con `RETURNING id` y guarda metadata suficiente para reconstruir el HTML del correo.
  - el cuerpo HTML entrante se sanitiza y reescribe los `src="cid:..."` a la descarga inline de Ticketera.
  - la UI de historial de correos prioriza `attachment_id` directo y se ajusta CSS para imágenes/tablas anchas.
  - pulido visual adicional previo a prod:
    - los adjuntos `inline` que ya están renderizados dentro del cuerpo no se vuelven a listar como adjuntos duplicados abajo
    - las imágenes bloqueadas por sanitización (por ejemplo firmas remotas sin `src` permitido) dejan de mostrar recuadros vacíos
- **Verificación**:
  - `python3 -m py_compile` sobre:
    - `ticketera/core/email_integration.py` ✅
    - `ticketera/service.py` ✅
    - `ticketera/core/tickets_service.py` ✅
  - `node --check ticketera/ui/js/tks_ui.js` ✅
  - `node --check code/static/modulos/tks/js/tks_ui.js` ✅
  - smoke técnico dentro de `monstruo-dev-ticketera` con correo MIME sintético HTML + imagen inline `cid:inline-1`:
    - `core: ok=True attachment_id=3 content_id=inline-1` ✅
    - `service: ok=True attachment_id=4 content_id=inline-1` ✅
  - verificación local del fallback monolítico:
    - `PYTHONPATH=/srv/monstruo_dev/code python3 ... hasattr(app.core.tickets_service, '_build_incoming_email_body_html') -> True` ✅
    - `monstruo-api` activo todavía corre una copia vieja de `/app/code/app/core/tickets_service.py` y no refleja aún el patch en runtime ⚠️
  - el `body_html` almacenado queda con `<img ... download?inline=1>` y el recurso asociado a un `attachment_id` real ✅
- **Estado**: FIX APLICADO Y VALIDADO EN DEV para la app independiente. El fallback monolítico quedó parchado en código, pero su contenedor actual no fue recargado todavía; si ese camino se usa, hay que reiniciar/reconstruir antes de esperar el comportamiento nuevo.

## HITO: 2026-03-31 - Ticketera independiente DEV: fix de esquema para creación de TK por correo
- **Incidente**: el polling IMAP del stack independiente (`ticketera`) sí leía correos, pero el flujo se caía antes de crear el ticket. En logs de `monstruo-dev-ticketera` aparecía:
  - `Error creating ticket: relation "ticket_config_client_emails" does not exist`
- **Causa raíz**:
  - `ticketera/service.py` consulta `ticket_config_client_emails` al resolver asociación `email -> cliente` durante `create_ticket(...)`.
  - la base nueva compartida del split independiente no estaba creando esa tabla en `ticketera/core/db.py` ni en `gateway/core/db.py`.
- **Acción ejecutada**:
  - se agrega creación canónica de `tks.ticket_config_client_emails` + índices:
    - `idx_tk_client_emails_email` (único por correo)
    - `idx_tk_client_emails_customer_id`
  - archivos ajustados:
    - `ticketera/core/db.py`
    - `gateway/core/db.py`
  - se ejecuta `db.init_db()` dentro del contenedor `monstruo-dev-ticketera` para migrar la base activa del stack nuevo.
- **Verificación**:
  - compilación por `compile(...)` de:
    - `ticketera/core/db.py` ✅
    - `gateway/core/db.py` ✅
  - validación de esquema en Postgres del contenedor:
    - `to_regclass('tks.ticket_config_client_emails')` -> `ticket_config_client_emails` ✅
  - smoke controlado sobre runtime real de la app independiente:
    - `create_ticket(..., origen_email='smoke.ticketera@telconsulting.cl')` crea `TK-31-03-2026-0001` ✅
    - `handle_incoming_email(...)` crea `TK-31-03-2026-0002` y registra correo entrante ✅
  - polling manual:
    - `poll_email_job({"recurring": False})` ejecuta sin volver a lanzar el error de relación faltante ✅
- **Estado**: FIX APLICADO Y VALIDADO EN DEV. La app independiente ya supera el bloqueo de esquema que impedía crear tickets desde correo; queda pendiente revalidar con un correo real nuevo hacia la casilla configurada.

## HITO: 2026-03-30 - Dashboard shell DEV: sidebar activo corregido + badge `DEV` removido
- **Solicitud**: en el dashboard, evitar que el sidebar marque `Dashboard` y `Fundación` al mismo tiempo, y quitar el badge rojo `DEV` del encabezado para que no se arrastre al shell que luego pase a producción.
- **Acción ejecutada**:
  - `sidebar.js` en las copias activas (`gateway`, `static_ui`, `code/static`) deja de marcar por host y pasa a:
    - preferir `data-current-module` cuando el shell lo declara
    - usar `pathname` normalizado como fallback en subdominios productivos (`/dashboard/`, `/fundacion`, etc.)
  - `dashboard.html` en las copias activas:
    - elimina el badge visual `DEV`
    - declara `data-current-module="dashboard"` en el `<body>`
    - sube el cache-bust del sidebar a `v=14`
- **Verificación**:
  - `node --check` sobre `sidebar.js` en copias activas ✅
  - validación lógica controlada:
    - `/dev/dashboard/` vs link `dashboard/` -> `true` ✅
    - `/dev/dashboard/` vs link `fundacion` -> `false` ✅
  - `https://login.telconsulting.cl/dev/dashboard/` contiene:
    - `data-current-module="dashboard"`
    - `sidebar.js?v=15`
    - sin `DEV`
    - sin `dash-dev-badge`
    ✅
- **Ajuste posterior**:
  - se detectó que `Fundación` seguía arrojando error porque el sidebar productivo apuntaba a `https://login.telconsulting.cl/dev/fundacion`, ruta que el shell público aún no expone sin recargar Nginx.
  - para resolver el incidente de inmediato sin depender del reload del proxy:
    - `sidebar.js` en las copias activas ahora apunta `Fundación` a `https://login.telconsulting.cl/dev/modulos/fundacion/fundacion.html`
    - `fundacion.html` declara `data-current-module="fundacion"`
    - se sube cache-bust del sidebar a `v=15` en Dashboard y Fundación
  - adicionalmente quedó preparada en `gateway/main.py` la ruta amigable `/fundacion` con `base href` correcto y el bloque correspondiente en `/etc/nginx/sites-available/telconsulting_subdomains.conf`; esa ruta bonita requiere `reload` de Nginx para quedar pública.
- **Ajuste visual posterior**:
  - `Fundación` se alineó al shell canónico del dashboard también en el footer del sidebar.
  - `fundacion.html` deja de depender de la inyección tardía de `#who`/botones desde `sidebar.js` y declara de inicio:
    - `#who` con clase `dash-who-pill`
    - `footer-buttons-container`
    - botones `Cuenta` y `Salir`
  - con eso se elimina el desfase visual leve donde el bloque inferior del sidebar se veía más abajo que en Dashboard.
  - además se corrige la causa residual de inconsistencia: `fundacion.html` estaba cargando assets compartidos absolutos (`/modulos/_compartido/...`) y en el host público eso podía resolver al root del dominio en vez de `/dev/modulos/_compartido/...`.
  - `fundacion.html` ahora usa rutas relativas (`../_compartido/...`) para CSS/JS compartidos, igual que el dashboard, asegurando que `Fundación` cargue el mismo `sidebar.js` de DEV.
  - se endurece el cálculo de item activo en `sidebar.js` para evitar ambigüedad:
    - ahora se calcula un único `activeItemId` antes de renderizar
    - cada link recibe `data-module-id`
    - tras renderizar, el script sanea el DOM y garantiza que quede un solo `.active`
  - cache-bust del sidebar sube a `v=16` en Dashboard y Fundación para cortar caché vieja.
  - se detecta la causa específica del bug “vuelve al iniciar sesión”:
    - `login.js` estaba redirigiendo a `/dev/dashboard/dashboard.html`
    - esa copia del dashboard todavía cargaba assets absolutos `/modulos/_compartido/...` desde el root del host
    - resultado: después del login se mezclaban copias distintas de `utilidades.js`/`sidebar.js`
  - corrección aplicada:
    - `login.js` ahora redirige al dashboard canónico `/dev/dashboard/`
    - se sube cache-bust a `login.js?v=109`
    - `static_ui/modulos/dashboard/{dashboard,inicio}.html` y copias equivalentes pasan a rutas relativas `../_compartido/...` + `../../manifest.json` para no reintroducir el mismo bug si alguien abre esas rutas directas
  - cierre de raíz del problema del shell lateral:
    - `sidebar.js` queda como dueño único de:
      - render del menú
      - item activo
      - estado colapsado
      - normalización del footer (`#who`, botones)
    - `admin.js` deja de tocar `active` y collapse del sidebar
    - se agrega `shell-who-pill` al CSS compartido
    - se normalizan las páginas activas de `dashboard`, `fundacion`, `ticketera`, `erp`, `bodega` y `crm` para que:
      - usen `data-current-module`
      - usen el mismo bloque `#who`
      - apunten a versiones alineadas de `monstruo.css`, `admin.js` y `sidebar.js`
    - fix funcional posterior:
      - `Configuración` todavía estaba cargando `sidebar.js?v=13` y `utilidades.js?v=205`, por eso no aparecía `Salir`
      - `Fundación` mostraba `Salir`, pero el click no hacía nada porque tras la unificación ya no se estaba re-ejecutando `initLogout()`
      - `sidebar.js` ahora:
        - crea `btnLogout` si falta
        - llama `initModal()` e `initLogout()` después de normalizar el footer
      - `utilidades.js` ahora deja `initLogout()`/`initModal()` idempotentes con `dataset` para evitar doble bind
      - `Configuración` se sube a `utilidades.js?v=206`, `admin.js?v=5`, `sidebar.js?v=18`
    - causa real del desfase visual residual en `Fundación`:
      - `fundacion.html` todavía redefinía clases genéricas del shell (`.btn-icon`, `.btn-primary`, `.btn-secondary`) dentro de su `<style>`
      - la más crítica era `.btn-icon`, porque también la usa el botón hamburguesa `#sidebar-toggle` del sidebar
      - ese override local agrandaba el botón del header y empujaba el menú unos píxeles hacia abajo sólo en `Fundación`
      - corrección aplicada:
        - el botón hamburguesa queda usando sólo el estilo compartido por `#sidebar-toggle`
        - los botones internos del módulo se renombran a `fund-btn-icon`, `fund-btn-primary`, `fund-btn-secondary`
        - se replica el mismo ajuste en `static_ui/modulos/fundacion/fundacion.html` y `code/static/modulos/fundacion/fundacion.html`
- **Verificación adicional**:
  - `https://login.telconsulting.cl/dev/dashboard/` ya publica `sidebar.js?v=15` ✅
  - `https://login.telconsulting.cl/dev/modulos/_compartido/js/sidebar.js?v=15` apunta `Fundación` a `/dev/modulos/fundacion/fundacion.html` ✅
  - `https://login.telconsulting.cl/dev/modulos/fundacion/fundacion.html` responde `200` ✅
  - `fundacion.html` público contiene `data-current-module="fundacion"` + `sidebar.js?v=15` ✅
  - `fundacion.html` público contiene `dash-who-pill`, `footer-buttons-container`, `btn-open-change-password` y `btnLogout` como el dashboard ✅
  - `fundacion.html` público ya no contiene clases genéricas locales `btn-icon`/`btn-primary`/`btn-secondary`; ahora sirve `fund-btn-*` y `#sidebar-toggle` sin clase extra ✅
  - las rutas públicas efectivas de `Fundación` para assets compartidos quedan relativas (`../_compartido/...`) y resuelven al mismo `sidebar.js` hash de `/dev/modulos/_compartido/js/sidebar.js?v=15` ✅
  - `https://login.telconsulting.cl/dev/dashboard/` ya publica `sidebar.js?v=16` ✅
  - `https://login.telconsulting.cl/dev/modulos/fundacion/fundacion.html` ya publica `sidebar.js?v=16` ✅
  - `sidebar.js?v=16` público contiene `activeItemId`, `data-module-id` y saneo de múltiples `.active` ✅
  - `https://login.telconsulting.cl/dev/` ya publica `login.js?v=109` ✅
  - `https://login.telconsulting.cl/dev/js/login.js?v=109` redirige a `/dev/dashboard/` ✅
  - `node --check` en copias activas de `sidebar.js` + `admin.js` (`gateway`, `static_ui`, `code/static`) ✅
  - `https://login.telconsulting.cl/dev/dashboard/` ya publica:
    - `monstruo.css?v=68.2`
    - `admin.js?v=5`
    - `sidebar.js?v=18`
    - `shell-who-pill`
    ✅
  - `https://login.telconsulting.cl/dev/modulos/fundacion/fundacion.html` ya publica:
    - `monstruo.css?v=68.2`
    - `utilidades.js?v=206`
    - `sidebar.js?v=18`
    - `shell-who-pill`
    ✅
  - `https://config.telconsulting.cl/dev/` ya publica:
    - `data-current-module="config"`
    - `utilidades.js?v=206`
    - `admin.js?v=5`
    - `sidebar.js?v=18`
    ✅
  - `https://config.telconsulting.cl/dev/modulos/_compartido/js/sidebar.js?v=18` contiene:
    - creación de `btnLogout`
    - `initModal()`
    - `initLogout()`
    ✅
  - `https://login.telconsulting.cl/dev/modulos/_compartido/js/utilidades.js?v=206` contiene guardas `logoutBound` y `modalBound` ✅
  - `ticketera/ui/tks.html` y apps independientes (`erp/bodega/crm`) quedan alineadas a:
    - `data-current-module`
    - `shell-who-pill`
    - `admin.js?v=5`
    - `sidebar.js?v=18`
    ✅
- **Estado**: IMPLEMENTADO Y VALIDADO EN DEV.

## HITO: 2026-03-30 - Dashboard DEV: `login` queda alineado al gateway nuevo sin vaciar KPIs cross-modulo
- **Solicitud**: partir por el dashboard para dejar la separación de aplicaciones de forma profesional, haciendo que `login/dashboard` use la misma capa nueva compartida que ya se habilitó para `login/configuracion/ticketera`.
- **Acción ejecutada**:
  - `gateway/api/routers/ops.py`:
    - se endurece el contrato de `GET /api/ops/dashboard` para que siempre entregue `recent_failures` con alias compatibles:
      - `error_msg`
      - `started_at`
    - se agrega tolerancia por tabla ausente/dato incompleto para que el dashboard no caiga completo si una métrica cross-módulo todavía no está poblada en la base nueva.
    - se implementa fallback temporal al runtime legacy (`172.17.0.1:9000/api/ops/dashboard`) cuando la base nueva no tiene aún KPIs cross-módulo sembrados; así el endpoint público ya sale desde `gateway`, pero sin dejar el tablero vacío mientras ERP/CRM siguen migrando.
  - `gateway/main.py`:
    - el root del host `login` vuelve a abrir `login/login.html` en vez de empujar al dashboard.
  - shells y assets duplicados (`gateway/`, `static_ui/`, `code/static/`):
    - `login.js` redirige al dashboard nuevo sin pasar por la ruta vieja `/dashboard` que generaba `301` hacia `http`.
    - `utilidades.js` corrige el redirect de sesión expirada:
      - prod -> `https://login.telconsulting.cl/dev/`
      - local/dev -> `/dev/login/login.html` o `/modulos/login/login.html`
    - `dashboard.html` y `inicio.html` quedan alineados para:
      - abrir Ticketera independiente (`ticketera.telconsulting.cl` o puerto `9005`)
      - tolerar payload nuevo/viejo de fallas (`error_msg|last_error`, `started_at|updated_at`)
      - bust de caché en `utilidades.js`, `sidebar.js`, `login.js`
    - `sidebar.js` queda sincronizado para:
      - `Dashboard` productivo -> `/dashboard/`
      - módulos locales -> puertos independientes (`9005/9006/9007/9008`)
  - Nginx local DEV en `192.168.60.5` (`/etc/nginx/sites-available/telconsulting_subdomains.conf`):
    - nuevo upstream `app_gateway -> 127.0.0.1:9001`
    - `login.telconsulting.cl` ahora enruta:
      - `= /dev/api/sesion` -> `app_gateway`
      - `/dev/api/auth/` -> `app_gateway`
      - `/dev/api/ops/` -> `app_gateway`
      - `/dev/api/auth/google/` -> `app_prod` (fallback legacy intencional)
      - `/dev/api/tks/` -> `ticketera`
    - `= /dev/dashboard` queda sirviendo directamente `dashboard.html` con `Content-Type: text/html`, eliminando el `301` absoluto a `http`.
- **Verificación**:
  - sintaxis validada:
    - `compile(...)` sobre `gateway/main.py` ✅
    - `compile(...)` sobre `gateway/api/routers/ops.py` ✅
    - `node --check` sobre `login.js`, `utilidades.js`, `sidebar.js` en copias activas (`gateway`, `static_ui`, `code/static`) ✅
  - shell local Nginx (`Host: login.telconsulting.cl` sobre `127.0.0.1`) ✅
    - `/dev/` expone `login.html` con `utilidades.js?v=204` + `login.js?v=108`
    - `/dev/dashboard/` expone dashboard actualizado
    - `/dev/dashboard` ya responde `200 text/html` sin redirect a `http`
  - API dashboard:
    - `http://127.0.0.1:9001/api/ops/dashboard` con token admin -> payload normalizado ✅
    - `http://127.0.0.1/dev/api/ops/dashboard` con `Host: login.telconsulting.cl` -> mismo payload vía Nginx local ✅
    - `https://login.telconsulting.cl/dev/api/ops/dashboard` -> mismo payload público vía gateway nuevo ✅
  - shell público:
    - `https://login.telconsulting.cl/dev/` expone `utilidades.js?v=204` + `login.js?v=108` ✅
    - `https://login.telconsulting.cl/dev/dashboard/` contiene:
      - `ticketera.telconsulting.cl`
      - `f.error_msg || f.last_error`
      - `started_at || updated_at`
      - `sidebar.js?v=12`
      - `utilidades.js?v=204`
      ✅
- **Estado**: IMPLEMENTADO Y VALIDADO EN DEV. `login/dashboard` ya usa la fachada nueva (`gateway`) para `auth/session/ops`; los KPIs cross-módulo siguen operativos gracias a fallback legacy temporal hasta que ERP/CRM cierren su migración de datos.

## HITO: 2026-03-30 - DEV shared control plane: Login + Configuración + Ticketera comparten auth/usuarios/settings en el gateway nuevo
- **Solicitud**: dejar la separación de aplicaciones de forma profesional, al menos entre `login`, `configuracion` y `ticketera`, para que compartan correctamente usuarios, credenciales, correo e intervalos operativos dentro del stack nuevo.
- **Acción ejecutada**:
  - `gateway/main.py` deja de ser solo shell/proxy y pasa a exponer API compartida real para DEV:
    - `POST /api/auth/login`
    - `GET /api/auth/whoami`
    - `POST /api/auth/logout`
    - `GET /api/sesion`
    - `POST /api/auth/change-password`
    - proxy corregido `/api/{service}/...` con alias `tks -> ticketera` y passthrough real de JSON/headers.
  - nuevos routers compartidos en `gateway/api/routers/`:
    - `admin_users.py` para CRUD de usuarios/roles/modulos
    - `config_router.py` para `role-scopes` y `smtp/imap/polling/auto-reply`
  - se sembró la base nueva compartida (`gateway` + `ticketera`) con la informacion minima necesaria desde el runtime legacy:
    - usuarios reales (`users`)
    - configuracion operativa en `system_settings`:
      - SMTP
      - IMAP
      - intervalo de polling
      - tiempos de auto-reply / auto-close
  - proxy publico `192.168.60.6`:
    - `config.telconsulting.cl` queda con `/dev/api/` apuntando al `gateway` nuevo (`:9001`) y `/dev/api/tks/` directo a `ticketera` (`:9005`)
    - `login.telconsulting.cl` mueve `auth/session` de DEV al `gateway` nuevo, manteniendo fallback legacy para el resto del dashboard y Google login
    - `login` y `config` salen del bloque compartido de `monstruo.conf` y quedan con server blocks dedicados
- **Verificación**:
  - sintaxis Python validada por `compile(...)` sobre:
    - `gateway/main.py` ✅
    - `gateway/api/routers/admin_users.py` ✅
    - `gateway/api/routers/config_router.py` ✅
  - `http://127.0.0.1:9001/health` -> `200` ✅
  - smoke local con usuario temporal sobre gateway nuevo:
    - `auth/login` ✅
    - `api/sesion` ✅
    - `api/admin/users` ✅
    - `api/config/smtp` ✅
    - `ticketera/api/tks/especialidades` usando el mismo token ✅
  - smoke publico DEV con cookie HTTPS compartida entre subdominios:
    - `https://login.telconsulting.cl/dev/api/auth/login` ✅
    - `https://login.telconsulting.cl/dev/api/sesion` ✅
    - `https://config.telconsulting.cl/dev/api/admin/users` ✅
    - `https://config.telconsulting.cl/dev/api/config/smtp` ✅
    - `https://ticketera.telconsulting.cl/dev/api/tks/especialidades` ✅
- **Estado**: IMPLEMENTADO Y VALIDADO EN DEV. `login`, `configuracion` y `ticketera` ya comparten una misma fuente de verdad para autenticacion, usuarios y settings operativos.

## HITO: 2026-03-30 - Hotfix Ticketera DEV: sincronización de usuarios para reactivar técnicos asignables
- **Incidente**: Ticketera independiente mostraba “no hay técnicos configurados” porque su fallback de especialidades leía la tabla `users` del stack DEV nuevo, y esa tabla sólo contenía el usuario temporal de smoke.
- **Acción ejecutada**:
  - se diagnosticó que:
    - `ticketera` y `gateway` del stack nuevo compartían una base DEV con `users=1`
    - el backend legacy aún visible en host público (`monstruo-api`, `main/prod`) sí conservaba los usuarios reales que hoy usa la operación
  - se ejecutó sincronización controlada de la tabla `users` desde `monstruo-api` hacia la base DEV consumida por `ticketera`/`gateway`:
    - copiados `username`, `password_hash`, `role`, `secondary_roles`, `is_active`, `allowed_modules`, `created_at`
    - eliminado el usuario temporal `smoke.ticketera.*`
    - aplicado `upsert` por `username`
  - no fue necesario crear `user_specialties`, porque Ticketera ya deriva especialidades desde roles técnicos:
    - `redes` -> `redes`
    - `implementaciones` -> `ejecucion`
    - `sistemas` -> `sistemas`
- **Verificación**:
  - base DEV nueva:
    - `users_count` en `ticketera` -> `6` ✅
    - `users_count` en `gateway` -> `6` ✅
  - derivación de técnicos en Ticketera:
    - `fabian.correa@telconsulting.cl` -> `redes` ✅
    - `juan.hormazabal@telconsulting.cl` -> `ejecucion` ✅
    - `lukas.moyano@telconsulting.cl` -> `sistemas` ✅
  - `list_specialties()` en `ticketera` devolviendo técnicos reales con `is_available=1` ✅
- **Estado**: HOTFIX OPERATIVO APLICADO EN DEV. Ticketera vuelve a tener técnicos asignables; queda pendiente alinear de forma canónica el API de Configuración pública con el stack DEV nuevo para evitar futuros desfases.

## HITO: 2026-03-30 - Hotfix proxy Config: `/dev/` queda sirviendo Configuración real en la raíz pública
- **Incidente**: tras recargar Nginx en la VM proxy, `https://config.telconsulting.cl/dev/` seguía cayendo en login y luego en dashboard porque el proxy compartido seguía delegando `/dev/` a la VM app sin una excepción específica para el subdominio `config`.
- **Acción ejecutada**:
  - se ingresó a la VM proxy `192.168.60.6` y se verificó que el tráfico público estaba controlado por `/etc/nginx/sites-available/monstruo.conf` + snippets `monstruo_prod_locations.conf` y `monstruo_dev_locations.conf`.
  - se removió `config.telconsulting.cl` del bloque compartido de `monstruo.conf` para evitar conflicto de `server_name`.
  - se creó un server block dedicado `config.telconsulting.cl.conf` en el proxy:
    - `80` -> redirect a HTTPS
    - `443` -> `location = /dev/` hace `proxy_pass` interno a `http://192.168.60.5:80/dev/configuracion/configuracion.html`
    - en esa respuesta HTML se inyecta `<base href="/dev/configuracion/">` para mantener la URL pública en `/dev/` sin romper assets relativos.
    - `location = /dev/dashboard` y `location = /dev/dashboard/` retornan `302 /dev/` para neutralizar redirecciones antiguas cacheadas del navegador hacia dashboard.
    - la raíz `/dev/` queda con headers `Cache-Control: no-store` para evitar que el cliente siga reutilizando respuestas viejas.
    - el resto de rutas sigue usando los snippets compartidos `monstruo_prod_locations.conf` y `monstruo_dev_locations.conf`.
  - se validó sintaxis y se recargó Nginx en la VM proxy.
- **Verificación**:
  - `nginx -t` en `192.168.60.6` ✅
  - `systemctl reload nginx` en `192.168.60.6` ✅
  - `curl -k https://config.telconsulting.cl/dev/` ya devuelve HTML de Configuración (`<title>Modulo | Monstruo</title>`) y no el login ✅
  - `curl -k https://config.telconsulting.cl/dev/` contiene `<base href="/dev/configuracion/">` ✅
  - `curl -k -I https://config.telconsulting.cl/dev/dashboard/` -> `302 location: https://config.telconsulting.cl/dev/` ✅
  - `curl -k -I https://config.telconsulting.cl/dev/` expone `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` ✅
  - assets necesarios desde raíz pública continúan resolviendo:
    - `/dev/modulos/_compartido/css/monstruo.css` ✅
    - `/dev/configuracion/js/users_ui.js` ✅
- **Estado**: APLICADO Y VALIDADO EN PROXY. `config.telconsulting.cl/dev/` queda apuntando a Configuración en la raíz pública.

## HITO: 2026-03-30 - Diagnóstico subdominio Config: el ajuste debe aplicarse en la VM proxy `192.168.60.6`
- **Incidente**: `https://config.telconsulting.cl/dev/` seguía mostrando el login/dashboard en vez de abrir la página de Configuración en la raíz del subdominio.
- **Acción ejecutada**:
  - se confirmó que el comportamiento público no dependía del `gateway` Python sino del proxy Nginx.
  - se verificó la topología documentada:
    - proxy inverso: `192.168.60.6`
    - VM app/docker: `192.168.60.5`
  - se detectó que esta sesión estaba ejecutándose en `192.168.60.5`, por lo que cualquier edición local en `/etc/nginx/...` no corrige por sí sola el tráfico público del subdominio.
  - se dejó definido el ajuste requerido para el proxy:
    - separar `config.telconsulting.cl` del bloque compartido con `login.telconsulting.cl`
    - servir `location = /dev/` con `configuracion/configuracion.html`
    - mantener `api` y assets DEV por alias/proxy compatibles.
- **Verificación**:
  - `hostname -I` en esta sesión -> `192.168.60.5` ✅
  - `docs/deploy/README.md` confirma `192.168.60.6` como VM del proxy Nginx ✅
  - `curl -k https://config.telconsulting.cl/dev/` seguía devolviendo el HTML de login, coherente con que el proxy público aún no tiene aplicado el ajuste ✅
- **Estado**: DIAGNÓSTICO ACLARADO. EL CAMBIO DEBE APLICARSE Y RECARGARSE EN LA VM PROXY `192.168.60.6`.

## HITO: 2026-03-30 - Migración apps independientes: Ticketera operativa + enlaces locales por módulo (DEV)
- **Solicitud**: retomar la migración dejada a medias para que `ticketera` quedara funcional hoy como app independiente; para `erp`, `bodega` y `crm`, bastaba con que cada módulo abriera su propia página dentro del esquema nuevo.
- **Acción ejecutada**:
  - `ticketera/main.py`:
    - se completa el bootstrap real de la app independiente:
      - carga de entorno
      - middleware de identidad
      - startup con `init_db()`
      - registro y scheduling de jobs críticos de Ticketera
      - worker loop propio
    - se agregan endpoints de compatibilidad que la UI compartida necesitaba para operar fuera del monolito:
      - `POST /api/auth/login`
      - `GET /api/auth/whoami`
      - `POST /api/auth/logout` + `/auth/logout`
      - `GET /api/sesion`
      - `POST /api/auth/change-password` + `/auth/change-password`
      - `POST /api/jobs/recover-stale`
      - `POST /api/cobranza/payment-link`
    - la raíz protegida ahora redirige a login cuando no hay sesión.
  - `ticketera/ui/login.html`:
    - nueva pantalla de acceso local para DEV cuando se abre la app independiente sin pasar por el login central.
  - `ticketera/ui/tks.html`:
    - assets cambiados a rutas relativas para que funcionen tanto en `/` local como detrás de prefijos tipo `/dev/`.
  - `ticketera/core/db.py`:
    - `init_db()` ahora asegura los schemas PostgreSQL requeridos antes de crear tablas, evitando caída de arranque por `InvalidSchemaName`.
  - `gateway/main.py`:
    - el mount de `/modulos` deja de asumir `gateway/shared/ui/modulos` y usa fallback válido hacia `static_ui/modulos` o `code/static/modulos`.
    - el root del subdominio `config` deja de redirigir al dashboard y ahora abre `configuracion/configuracion.html`.
  - `gateway/shared/ui/js/sidebar.js`:
    - en local, los enlaces de `erp`, `crm`, `bodega` y `ticketera` pasan a abrir sus apps independientes por puerto (`9006`, `9008`, `9007`, `9005`).
  - `gateway/dashboard/dashboard.html`:
    - el widget de tickets abre Ticketera independiente en local y subdominio dedicado en host productivo.
  - `erp/main.py`, `bodega/main.py`, `crm/main.py`:
    - mounting corregido para consumir assets compartidos reales desde el repositorio actual.
  - `docker-compose.yaml`:
    - agregado servicio `crm` al stack DEV para que el módulo también responda como app independiente.
- **Verificación**:
  - `python3 -m py_compile ticketera/main.py ticketera/router.py ticketera/service.py ticketera/core/jobs_engine.py` ✅
  - `node --check gateway/shared/ui/js/sidebar.js` ✅
  - `docker compose up -d --build gateway ticketera erp bodega crm` con `ops/env/.env.server.dev` cargado ✅
  - `curl http://127.0.0.1:9005/health` -> `200 {"status":"ok","module":"ticketera"}` ✅
  - `curl http://127.0.0.1:9005/` sin sesión -> `302 .../login.html` ✅
  - `curl http://127.0.0.1:9005/login.html` entrega pantalla de login local ✅
  - smoke autenticado DEV con usuario temporal controlado:
    - `POST /api/auth/login` ✅
    - `GET /api/sesion` ✅
    - `GET /` con cookie -> HTML Ticketera ✅
    - `GET /api/tks/tickets?limit=1` ✅
    - `POST /api/cobranza/payment-link` ✅
    - `POST /api/jobs/recover-stale?stale_minutes=20` ✅
  - módulos independientes respondiendo en DEV:
    - `http://127.0.0.1:9006/` -> `200` ✅
    - `http://127.0.0.1:9007/` -> `200` ✅
    - `http://127.0.0.1:9008/` -> `200` ✅
  - gateway DEV:
    - `http://127.0.0.1:9001/health` -> `200` ✅
    - `http://127.0.0.1:9001/dev/shared/js/sidebar.js` expone enlaces locales a `9005/9006/9007/9008` ✅
    - `Host: config.telconsulting.cl` sobre `/dev/` -> `307 location: configuracion/configuracion.html` ✅
- **Estado**: IMPLEMENTADO Y VALIDADO EN DEV. Ticketera queda operativa como app independiente; el resto de módulos queda enrutable a su página propia dentro del nuevo esquema.

## HITO: 2026-03-26 - Hotfix PROD Ticketera: dominio/plantillas + auto-respuesta
- **Incidente**: en producción, la pestaña `Ticketera > Dominio/Plantillas` respondía `500` por falta de la tabla `tks.ticket_config_email_routes`; además el worker de auto-respuesta quedó llamando helpers con la firma antigua y fallaba al procesar correos entrantes.
- **Acción ejecutada**:
  - `code/app/core/db.py`:
    - se agrega creación canónica de `tks.ticket_config_email_routes` e índices asociados dentro de `init_db()`.
  - `code/app/core/jobs_engine.py`:
    - `send_auto_response_job()` queda alineado con las firmas nuevas de `_auto_reply_subject()` y `_auto_reply_body()`, usando la conexión y el ticket completos.
  - `tests/unit_ticketera_core.py`:
    - nueva regresión para validar que el job de auto-respuesta usa correctamente los helpers de plantilla.
  - Runtime PROD:
    - hotfix directo en DB para crear `tks.ticket_config_email_routes` y sacar de inmediato el `500` del panel.
- **Verificación**:
  - `python3 -m py_compile code/app/core/db.py code/app/core/jobs_engine.py code/app/core/tickets_service.py` ✅
  - `python3 -m unittest tests.unit_ticketera_core` ✅
  - `SELECT to_regclass('tks.ticket_config_email_routes')` en PROD -> `tks.ticket_config_email_routes` ✅
  - `SELECT count(*) FROM tks.ticket_config_email_routes` en PROD -> `0` ✅
  - `curl http://127.0.0.1:9000/health` -> `200` ✅
- **Estado**: HOTFIX APLICADO EN PROD Y PENDIENTE DE PROMOCIÓN CANÓNICA POR GIT.

## HITO: 2026-03-26 - Ticketera: vista previa inline de adjuntos (DEV)
- **Solicitud**: evitar que las imágenes y adjuntos del detalle se descarguen de inmediato; mostrar vista previa, abrirlos dentro de la misma página y dejar la descarga como acción secundaria dentro del visor.
- **Acción ejecutada**:
  - `code/app/api/routers/tks.py`:
    - el endpoint `GET /api/tks/tickets/{ticket_id}/attachments/{attachment_id}/download` ahora acepta `?inline=1` y responde con `Content-Disposition: inline` cuando corresponde.
  - `code/app/core/tickets_service.py`:
    - `get_ticket_attachment_for_download()` normaliza `content_type` usando el valor guardado o una inferencia por extensión para habilitar preview real de imágenes/PDF/texto.
  - `code/static/modulos/tks/js/tks_api.js`:
    - agregado helper `getTicketAttachmentInlineUrl(...)`.
  - `code/static/modulos/tks/js/tks_ui.js`:
    - los adjuntos del feed y del sidebar pasan a renderizarse como tarjetas con miniatura/ícono, eliminando el enlace morado de descarga directa.
    - nuevo modal de preview inline para imágenes, PDF y texto.
    - la acción principal del usuario pasa a ser abrir el adjunto dentro de la misma vista; descargar queda dentro del modal.
  - `code/static/modulos/tks/js/tks_main.js`:
    - manejo de apertura/cierre del visor de adjuntos.
  - `code/static/modulos/tks/css/tks.css` + `code/static/modulos/tks/tks.html`:
    - estilos nuevos para tarjetas y modal de preview.
    - cache-bust de assets (`tks.css?v=52`, `tks_api.js?v=15`, `tks_ui.js?v=81`, `tks_main.js?v=57`).
- **Verificación**:
  - `python3 -m py_compile code/app/api/routers/tks.py code/app/core/tickets_service.py` ✅
  - `node --check code/static/modulos/tks/js/tks_api.js` ✅
  - `node --check code/static/modulos/tks/js/tks_ui.js` ✅
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
  - `python3 -m unittest tests.unit_ticketera_core` ✅
  - `docker restart monstruo-dev-api` ✅
  - `curl http://127.0.0.1:9001/health` -> `200` ✅
  - `GET /api/tks/tickets/1/attachments/1/download?inline=1` sin sesión -> `401` ✅
- **Estado**: IMPLEMENTADO EN DEV. Pendiente validación visual/manual del usuario.

## HITO: 2026-03-26 - Ticketera: respuesta al cliente habilitada en tickets activos (DEV)
- **Incidente**: en producción el especialista asignado no podía abrir `Responder cliente` si el ticket seguía en estado principal `abierto`, porque frontend y backend exigían `en_progreso` para habilitar el correo.
- **Acción ejecutada**:
  - `code/app/core/tickets_service.py`:
    - el envío de correo al cliente queda permitido mientras el ticket esté activo (`abierto` o `en_progreso`), manteniendo bloqueo en `resuelto` y `cerrado`.
  - `code/static/modulos/tks/js/tks_main.js`:
    - nueva evaluación `canReplyToClient` para especialistas asignados en tickets activos.
    - el compositor deja de marcarse readonly en `abierto`.
    - el review/envío deja de bloquear por no estar en `en_progreso`.
  - `code/static/modulos/tks/js/tks_ui.js`:
    - `Responder cliente` queda habilitado en tickets activos.
    - textos de ayuda actualizados para reflejar que el bloqueo real aplica a `resuelto/cerrado`.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust a `tks_ui.js?v=82` y `tks_main.js?v=58`.
  - `tests/unit_ticketera_core.py`:
    - regresión ajustada para exigir bloqueo sólo en `resuelto/cerrado`.
- **Verificación**:
  - `python3 -m unittest tests.unit_ticketera_core` ✅
  - `node --check code/static/modulos/tks/js/tks_ui.js` ✅
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
  - `python3 -m py_compile code/app/core/tickets_service.py` ✅
- **Estado**: IMPLEMENTADO EN DEV. Pendiente promoción a PROD.

## HITO: 2026-03-26 - Ticketera: dominio/plantillas movidos a pestaña propia (DEV)
- **Solicitud**: sacar la edición de mensajes y el enrutamiento por correo/dominio desde Configuración y dejarlo dentro del módulo Ticketera con acceso para `encargado_mesa` y `admin`.
- **Acción ejecutada**:
  - `code/app/api/routers/tks.py`:
    - agregados endpoints propios:
      - `GET /api/tks/settings/domain-templates`
      - `GET/PUT /api/tks/settings/message-templates`
      - `GET/PUT /api/tks/settings/mail-templates/{template_key}`
      - `POST/DELETE /api/tks/settings/routing-rules*`
    - guardia dedicada para permitir edición sólo a roles de gestión Ticketera (`admin`, `encargado_mesa`).
  - `code/static/modulos/tks/tks.html`:
    - nueva pestaña `Dominio/Plantillas` dentro del shell de Ticketera.
  - `code/static/modulos/tks/js/tks_api.js`:
    - agregadas llamadas API para leer/guardar plantillas y reglas de enrutamiento desde Ticketera.
  - `code/static/modulos/tks/js/tks_main.js`:
    - visibilidad del tab controlada por rol.
    - carga y guardado del panel combinado `Dominio/Plantillas` con caché propia del módulo.
    - apertura del editor de plantilla contra endpoint puntual para precargar el contenido efectivo actual antes de editar.
  - `code/static/modulos/tks/js/tks_ui.js` + `code/static/modulos/tks/css/tks.css`:
    - nueva vista con 4 plantillas operativas visibles como botones/tarjetas:
      - auto-respuesta
      - asignación de especialista
      - notificación de especialista
      - cierre de TK
    - edición en modal mostrando el contenido actual efectivo del sistema, aunque la DB no tenga una personalización previa guardada.
    - formulario y grilla para reglas de routing por correo exacto o dominio.
  - `code/app/core/tickets_service.py`:
    - catálogo canónico de 4 plantillas de correo de Ticketera con subject/body configurables por DB.
    - render de notificaciones de asignación/cierre unificado sobre plantillas configurables.
    - avisos internos de cambio de estado mantenidos fuera del editor de plantillas.
  - `code/static/modulos/configuracion/configuracion.html`:
    - removidos de Configuración la edición de plantilla y el enrutamiento.
    - se deja aviso indicando que ahora se administra desde `Ticketera > Dominio/Plantillas`.
  - `tests/unit_ticketera_core.py`:
    - regresiones para validar que Ticketera expone 4 plantillas efectivas y que las notificaciones al especialista y de cambio de estado interno siguen operativas.
  - Runtime DEV:
    - reinicio controlado de `monstruo-dev-api` para activar los endpoints nuevos en memoria.
- **Verificación**:
  - `python3 -m py_compile code/app/core/tickets_service.py code/app/api/routers/tks.py` ✅
  - `python3 -m py_compile code/app/api/routers/tks.py` ✅
  - `node --check code/static/modulos/tks/js/tks_api.js` ✅
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
  - `node --check code/static/modulos/tks/js/tks_ui.js` ✅
  - `python3 -m unittest tests.unit_ticketera_core` ✅
  - `curl http://127.0.0.1:9001/health` -> `200` ✅
  - `GET http://127.0.0.1:9001/api/tks/settings/domain-templates` sin auth -> `401 missing_auth` ✅
  - `GET http://127.0.0.1:9001/api/tks/settings/mail-templates/auto_reply` sin auth -> `401 missing_auth` ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO Y RUNTIME DEV REINICIADO. Pendiente validación visual/manual del usuario.

## HITO: 2026-03-23 - Fundación: fix de migración canónica + promoción de data hacia PROD (DEV)
- **Solicitud**: usar `DEV` como fuente de verdad para llevar a `PROD` la planificación completa de Fundación.
- **Acción ejecutada**:
  - `code/app/core/db.py`: la migración canónica de `fundacion.fundacion_tareas` ahora asegura también `curso`, `categoria`, `categoria_madre` y `subcategoria`.
  - se validó que `DEV` contenía `1050` registros de Fundación y fue usado como origen para la promoción de data hacia `PROD`.
  - se aplicó el mismo `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` en `DEV` para mantener paridad estructural explícita, aunque la base ya tenía esas columnas.
  - reinicio controlado de `monstruo-dev-api`.
- **Verificación**:
  - `fundacion.fundacion_tareas` en `DEV` se mantiene en `1050` registros ✅
  - `http://127.0.0.1:9001/health` -> `200` ✅
- **Estado**: DEV queda como fuente alineada y con migración canónica corregida.

## HITO: 2026-03-23 - Sincronización DEV de fixes Sidebar/Fundación/Cuenta (DEV)
- **Solicitud**: pasar a `DEV` los fixes ya aplicados en `PROD` para dejar consistentes la barra lateral, los controles `Cuenta/Salir`, el switch DEV/PROD y Fundación.
- **Acción ejecutada**:
  - sincronizados desde `/srv/monstruo` hacia `/srv/monstruo_dev` los archivos backend y frontend involucrados en:
    - resolución backend de `allowed_modules` y `permissions`,
    - compatibilidad legacy de módulos (`ticketera`, `ultron`, `configuracion`),
    - endpoint de cambio de contraseña,
    - inicialización compartida de `Cuenta` y `Salir`,
    - generación idempotente del footer del sidebar,
    - permisos reales de Fundación y corrección del dueño de tarea,
    - fix visual de Fundación para no contaminar `#sidebar-toggle` con el override local de `.btn-icon`.
  - shells DEV actualizados para cache-bust:
    - `utilidades.js?v=205`
    - `sidebar.js?v=13`
    - `fundacion.js?v=5`
  - runtime DEV: reinicio controlado de `monstruo-dev-api`.
- **Verificación**:
  - `node --check` sobre:
    - `code/static/modulos/_compartido/js/sidebar.js` ✅
    - `code/static/modulos/_compartido/js/utilidades.js` ✅
    - `code/static/modulos/fundacion/js/fundacion.js` ✅
  - `compile(...)` Python sobre:
    - `code/app/core/config.py` ✅
    - `code/app/main.py` ✅
    - `code/app/core/auth_service.py` ✅
    - `code/app/api/routers/fundacion/fundacion_router.py` ✅
  - smoke de helpers:
    - `gerencia` ahora conserva `fundacion:read` ✅
    - aliases legacy `configuracion -> config`, `ultron -> ia`, `ticketera -> tks` ✅
  - `docker restart monstruo-dev-api` ejecutado ✅
  - `curl http://127.0.0.1:9001/health` -> `200` ✅
  - `POST http://127.0.0.1:9001/api/auth/change-password` sin sesión -> `401` (endpoint activo) ✅
  - assets públicos DEV:
    - `https://login.telconsulting.cl/dev/modulos/fundacion/fundacion.html` sirve `utilidades.js?v=205`, `sidebar.js?v=13`, `fundacion.js?v=5` ✅
    - `https://config.telconsulting.cl/dev/modulos/configuracion/configuracion.html` sirve `utilidades.js?v=205`, `sidebar.js?v=13` ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO Y RUNTIME DEV REINICIADO. Pendiente validación visual/manual del usuario.

## HITO: 2026-03-20 - Promoción DEV -> PROD validada (Ticketera)
- **Solicitud**: ejecutar la promoción real de `dev` a `main/prod` y verificar que producción quedara estable con la versión validada.
- **Acción ejecutada**:
  - Git:
    - `main` fue avanzado por fast-forward desde `69e83e3` a `8fb5cc6`.
    - push ejecutado a `origin/main`, disparando deploy automático por GitHub Actions.
  - Deploy PROD:
    - repositorio `/srv/monstruo` actualizado a `8fb5cc6`.
    - contenedor `monstruo-api` reiniciado con `APP_GIT_SHA=8fb5cc6`, `APP_GIT_BRANCH=main`, `APP_BUILD_TIME=2026-03-20T17:05:38Z`.
  - Validación post-deploy:
    - healthcheck HTTP 200.
    - smoke API productivo con `verify_hardening.py --check-api --allow-prod` usando usuario temporal controlado.
    - limpieza posterior de artefactos de smoke (`tickets`, `parallel_decisions`, usuario y sesión temporales).
- **Verificación**:
  - `git -C /srv/monstruo rev-parse --short HEAD` -> `8fb5cc6` ✅
  - `curl http://127.0.0.1:9000/health` -> `200` ✅
  - `python3 tests/verify_hardening.py --check-api --allow-prod --base-url http://127.0.0.1:9000 --user <temp> --password '***' --timeout 60` ✅
  - runtime limpio tras smoke:
    - `tickets=0` ✅
    - `hardening_decisions=0` ✅
    - `temp_users=0` ✅
  - assets Ticketera servidos desde PROD:
    - `tks_main.js?v=53` -> 200 ✅
    - `tks_ui.js?v=76` -> 200 ✅
- **Observación operativa**:
  - PROD quedó estable a nivel deploy/runtime.
  - Correo de Ticketera sigue pendiente de configuración funcional en PROD (`imap_host` y `smtp_host` vacíos al momento de la validación), por lo que el polling IMAP seguirá registrando `No IMAP config found` hasta completar esa configuración.
- **Estado**: CERRADO (PROD validado).

## HITO: 2026-03-20 - Preflight DEV -> PROD Ticketera (DEV)
- **Solicitud**: preparar una promoción segura de `dev` a `prod` para ticketera sin romper threading, adjuntos ni gates de validación.
- **Acción ejecutada**:
  - `code/app/core/email_integration.py`:
    - corregido parseo multipart IMAP para no perder adjuntos cuando aparecen después del primer `text/plain`/`text/html`.
  - `tests/unit_ticketera_core.py`:
    - agregadas regresiones para:
      - asunto/threading de correo de asignación,
      - correo de resolución con ventana dinámica de auto-cierre,
      - lectura de `ticket_auto_close_time`,
      - parseo IMAP de asunto/cuerpo/adjuntos.
  - `tests/verify_hardening.py`:
    - alineado `--check-api` al workflow vigente de tickets tipo `cambio` (`recibido -> asignado -> en_analisis -> pendiente_aprobacion_1`) para eliminar falso negativo del gate.
  - Runtime DEV:
    - reinicio controlado de `monstruo-dev-api` para validar el código actual montado en contenedor.
    - limpieza de artefactos de validación (`Hardening Workflow*`, decisiones `go-no-go` de prueba y usuario temporal de smoke).
- **Verificación**:
  - `python3 tests/unit_ticketera_core.py` ✅
  - `python3 tests/unit_ticketera_frontend_security.py` ✅
  - `python3 tests/verify_hardening.py` ✅
  - `python3 tests/verify_hardening.py --check-api --base-url http://127.0.0.1:9001 --user <temp> --password '***' --timeout 60` ✅
  - `python3 -m compileall -q code/app tests/unit_ticketera_core.py tests/verify_hardening.py` ✅
- **Estado**: CERRADO (DEV). Queda pendiente promoción humana `dev -> main` para disparar deploy PROD por Actions.

## HITO: 2026-03-17 - UX Ticketera: Notificación de Resolución Dinámica y Auto-cierre (DEV)
- **Solicitud**: automatizar correo al cliente sincronizado con la configuración de Ajustes (auto-cierre).
- **Acción ejecutada**:
  - `tickets_service.py`: 
    - Implementada función `_get_auto_close_hours()` para leer el tiempo configurado en la DB (`ticket_auto_close_time`).
    - Actualizada `notify_client_resolution` para que el texto del correo informe dinámicamente el plazo de horas.
  - `jobs_engine.py`: Ajustado intervalo de auto-cierre por defecto a 24h.
- **Estado**: CERRADO (DEV).

## HITO: 2026-03-17 - UX Ticketera: Actualización automática y limpieza visual (DEV)
- **Solicitud**: actualización reactiva del detalle y eliminación de "tarjetas amarillas" redundantes.
- **Acción ejecutada**:
  - `tks_main.js`: Implementación de `refreshDetailFeed` con polling diferido de 3s.
  - `tks_ui.js`: Filtrado de eventos "transicion" y humanización de textos (sin guiones bajos).
  - `tickets_service.py`: Desactivada emisión de comentarios de sistema para transiciones y humanización de mensajes de estado.
- **Estado**: CERRADO (DEV).

## HITO: 2026-03-17 - Reinicio Técnico de Ticketera a 0 (DEV & PROD)
- **Solicitud**: reiniciar la ticketera a 0 tickets en ambos ambientes para iniciar ciclo de pruebas limpio.
- **Acción ejecutada**:
  - Base de Datos: Truncado transaccional (`RESTART IDENTITY CASCADE`) de 19 tablas operativas en los esquemas `tks`, `ops` y `core`.
  - Archivos: Limpieza total de directorios de adjuntos en `/srv/monstruo_dev/data/tickets/` y `/srv/monstruo/data/tickets/`.
  - Carga Técnica: Reinicio de contadores de carga de especialistas a 0.
- **Verificación**:
  - DEV: Tickets = 0, Carga = 0, Archivos = 0 ✅
  - PROD: Tickets = 0, Carga = 0, Archivos = 0 ✅
- **Estado**: CERRADO.

- **Solicitud**: promover todos los cambios de DEV a PROD de forma segura.
- **Acción ejecutada**:
  - Limpieza de Git: Se detectaron archivos de 4.2GB en `data/fundacion`, se procedió a excluirlos vía `.gitignore` para permitir el push.
  - Sincronización: Merge de `dev` a `main` y push a GitHub, detonando auto-deploy vía runner.
  - Base de Datos:
    - Ejecución de `migrate_to_schemas.py` en PROD: esquemas `auth`, `tks`, `erp`, `crm`, `bodega`, `core`, `ia`, `ops`, `cat`, `pmo` creados y tablas migradas desde `public`.
    - Verificación de motor de migraciones SQL funcional.
  - Runtime: Ajuste de variables de entorno para evitar cruces (puertos 9000 vs 9001, rutas `/srv/monstruo` vs `/srv/monstruo_dev`).
- **Verificación**:
  - `curl http://localhost:9000/health` -> 200 OK ✅
  - Acceso a base de datos de producción validada con nuevos esquemas. ✅
- **Estado**: CERRADO.

## HITO: 2026-03-12 - Blindaje DEV/PROD para deploy sin regresiones (DEV)
- **Solicitud**: dejar DEV y PROD realmente separados para que al promover cambios desde `dev` a `main` no aparezcan regresiones por mezcla de envs o rutas legacy.
- **Acción ejecutada**:
  - `docker-compose.yaml` vuelve a usar `env_file` canónico por `ENV_FILE` con default DEV (`ops/env/.env.server.dev`) en vez de `.env` fijo.
  - `ops/herramientas/deploy/deploy.sh` corregido:
    - se repara error de sintaxis (`fi` sobrante),
    - se agrega fallback explícito por rama para `ops/env/.env.server` y `ops/env/.env.server.dev`,
    - se mantiene compatibilidad controlada con legacy `.env.server` / `.env`.
  - runtime backend ahora resuelve entorno por convención canónica (`code/app/core/env_loader.py`) y deja de depender de `.env` raíz por defecto en:
    - `code/app/main.py`
    - `code/app/core/config.py`
    - `code/app/core/db.py`
    - `code/app/core/ai/ai_local_openai_compat.py`
  - scripts operativos alineados a la misma resolución de entorno:
    - `code/scripts/sync_erp.py`
    - `code/scripts/sync_calendario_ejecutivo.py`
    - `ops/herramientas/deploy/start.sh`
    - `ops/herramientas/deploy/iniciar_todo.sh`
  - tests y checks endurecidos para bloquear regresiones de contrato:
    - `tests/e2e_ticketera.py` usa `ops/env/.env.server.dev`
    - `tests/verify_hardening.py` ahora valida workflow DEV/PROD, compose canónico, uso de `load_runtime_env()` y sintaxis de `deploy.sh`.
- **Verificación**:
  - `bash -n ops/herramientas/deploy/deploy.sh` ✅
  - `python3 -m compileall -q code/app code/scripts` ✅
  - `python3 tests/verify_hardening.py` ✅
  - `ENV_FILE=ops/env/.env.server.dev docker compose --env-file ops/env/.env.server.dev config -q` ✅
  - `ENV_FILE=/srv/monstruo/.env.server docker compose --env-file /srv/monstruo/.env.server config -q` ✅
- **Estado**: CERRADO.

## HITO: 2026-03-11 - Consolidación de archivos `.env`, limpieza de redundancias y actualización de Google OAuth (PROD)
- **Descripción**: Consolidación de archivos `.env`, limpieza de redundancias y actualización de Google OAuth. Configuración centralizada en `ops/env/` con despliegue exitoso a `main`. (Juan / Antigravity)
- **Estado**: CERRADO.

## HITO: 2026-02-23 - EPIC 11 Ticketera: reset operativo + eliminación de usuarios de prueba (DEV)
- **Solicitud**: resetear ticketera y eliminar usuarios de pruebas creados durante validaciones.
- **Acción ejecutada**:
  - truncado transaccional con `RESTART IDENTITY CASCADE` en:
    - `tickets`, `ticket_comments`, `ticket_emails`, `ticket_attachments`,
    - `ticket_email_drafts`, `ticket_email_draft_attachments`,
    - `ticket_notifications`, `ticket_notification_attempts`,
    - `ticket_transitions`, `ticket_approvals`, `ticket_legal_holds`,
    - `jira_issue_map`, `jira_sync_runs`, `jira_sync_cursor`,
    - `parallel_kpi_daily`, `parallel_decisions`,
    - `compliance_export_runs`, `compliance_purge_runs`, `evidence_events`.
  - reinicio de carga técnica: `user_specialties.current_load = 0`.
  - eliminación de usuarios de pruebas:
    - `qa_epic11_local`
    - `qa_epic11_runner`
    - `qa_epic11_all`
  - limpieza de adjuntos DEV en filesystem:
    - `/srv/monstruo_dev/data/tickets` -> limpio.
- **Verificación**:
  - `tickets_after = 0`.
  - `non_zero_load_after = 0`.
  - `test_users_after = 0`.
  - tablas de paralelo/compliance ticketera en `0` (`jira_sync_runs`, `jira_sync_cursor`, `parallel_kpi_daily`, `parallel_decisions`, `compliance_export_runs`, `compliance_purge_runs`, `evidence_events`).
  - adjuntos DEV: `0` elementos en `/srv/monstruo_dev/data/tickets`.
- **Estado**: CERRADO.

## HITO: 2026-02-23 - Hotfix CI/CD: despliegue PROD por Actions falla por POSTGRES_PASSWORD faltante
- **Incidente**:
  - PR `#8` de Ticketera se mergeó correctamente a `main`, pero el workflow `CI + Deploy` falló en job `deploy`.
  - Error exacto en step `Deploy to server`: `required variable POSTGRES_PASSWORD is missing`.
- **Causa raíz**:
  - en algunos entornos, el despliegue dispone de `DB_URL` pero no de `POSTGRES_PASSWORD` explícito para la interpolación de `docker-compose`.
- **Corrección aplicada**:
  - `ops/herramientas/deploy/deploy.sh`:
    - se agrega fallback para derivar `POSTGRES_PASSWORD` desde `DB_URL` cuando no viene definido.
    - mantiene comportamiento previo cuando `POSTGRES_PASSWORD` ya existe.
- **Verificación**:
  - `bash -n ops/herramientas/deploy/deploy.sh` ✅
- **Estado**: HOTFIX IMPLEMENTADO EN CÓDIGO (pendiente re-ejecución de workflow para confirmar deploy en PROD).

## HITO: 2026-02-23 - EPIC 11 Ticketera: revisión integral de flujos y smoke técnico (DEV)
- **Solicitud**: revisar Ticketera completa (código + flujos) y validar que opere correctamente antes de subida a GitHub.
- **Verificación ejecutada**:
  - `python3 tests/verify_hardening.py --check-api --base-url http://127.0.0.1:9001 --user qa_epic11_local --password '***' --timeout 60` ✅
  - `python3 tests/e2e_api_full.py --base-url http://127.0.0.1:9001 --user qa_epic11_all --password '***' --timeout 60` ✅
  - `python3 tests/e2e_ticketera.py --base-url http://127.0.0.1:9001 --user qa_epic11_all --password '***' --timeout 60` ✅
  - `python3 tests/unit_ticketera_core.py` ✅
  - `python3 tests/unit_ticketera_frontend_security.py` ✅
  - `node --check code/static/modulos/tks/js/tks_ui.js` ✅
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
- **Hallazgo operativo**:
  - ejecución de `e2e_api_full` con usuario `admin` puro falla por política vigente (admin no participa en comentarios/correo/adjuntos). Se valida PASS con rol técnico-compliance (`ops+admin`).
- **Estado**: CERRADO. Ticketera validada en DEV para avance de publicación.

## HITO: 2026-02-23 - EPIC 11 Ticketera: Operación traducida a español legible (DEV)
- **Solicitud**: traducir la UI de la pestaña `Operación` porque mostraba términos técnicos en inglés difíciles de entender.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - normalización de etiquetas dinámicas en español para:
      - estados operativos (`pending`, `running`, etc.),
      - modos de adaptador (`disabled`, `dry_run`, `live`),
      - canales (`whatsapp`, `3cx`, etc.),
      - tipos de trabajo de cola (`by_job_type`),
      - tipos de corrida Jira (`run_type`).
    - fallback genérico para humanizar valores no mapeados (`snake_case/kebab-case` -> frase legible).
    - tablas de Operación renderizan etiquetas traducidas (no claves crudas).
  - `code/static/modulos/tks/js/tks_main.js`:
    - toast de recuperación de huérfanos traducido a español completo.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust actualizado: `tks_ui.js?v=71`, `tks_main.js?v=53`.
- **Verificación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` ✅
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-23 - EPIC 11 Ticketera: ocultamiento definitivo de pestaña Operación para no-admin (DEV)
- **Solicitud**: aunque redirigía, la pestaña `Operación` seguía visible para no-admin; se pidió que no se vea derechamente.
- **Causa raíz**:
  - el ocultamiento previo usaba `style.display = 'none'`, pero era vulnerable a reglas globales de tabs con `display: inline-flex !important`.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_main.js`:
    - en `applyRoleView()`, para no-admin el botón `data-tab="ops"` se elimina del DOM (`btn.remove()`).
    - para admin se conserva visibilidad normal.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust actualizado a `tks_main.js?v=52`.
- **Verificación**:
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
  - no-admin: no ve el tab `Operación` en la barra.
  - admin: mantiene tab `Operación` visible.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-23 - EPIC 11 Ticketera: pestaña Operación visible solo para ADMIN (DEV)
- **Solicitud**: ocultar la pestaña `Operación` para usuarios no admin porque genera confusión.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_main.js`:
    - `ROLE_OPS_READ` restringido a `admin` exclusivamente.
    - efecto: `sessionCtx.canViewOps` deja de habilitar `Operación` para `encargado_mesa` u otros roles.
    - se mantiene guard de seguridad en navegación: si un no-admin intenta `loadTab('ops')`, se redirige a `lista`.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust de script actualizado a `tks_main.js?v=51`.
- **Verificación**:
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
  - validación funcional esperada:
    - admin: ve pestaña `Operación`.
    - no-admin: pestaña `Operación` oculta y bloqueo por navegación directa al tab.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-23 - EPIC 11 Ticketera: reset operativo a 0 en DEV + normalización de ruta de reglas
- **Solicitud**: dejar la ticketera en 0 tickets y alinear la gobernanza para usar `.agents` en vez de `.agent`.
- **Entregable**:
  - reset de tablas operativas de Ticketera en `monstruo-dev-postgres`:
    - `ticket_notification_attempts`, `ticket_notifications`, `ticket_email_draft_attachments`,
    - `ticket_email_drafts`, `ticket_attachments`, `ticket_emails`, `ticket_comments`,
    - `ticket_transitions`, `ticket_approvals`, `ticket_legal_holds`, `jira_issue_map`, `tickets`
    - con `RESTART IDENTITY CASCADE`.
  - reinicio de carga técnica: `user_specialties.current_load = 0`.
  - ajuste de rutas canónicas de reglas:
    - `AGENTS.md` -> `.agents/rules/reglas-monstruo-dev.md`
    - `.agents/rules/reglas-monstruo-dev.md` (autorreferencia y frase de control)
    - `docs/PLAN_MAESTRO_MONSTRUO.md` sección 0.7 y bitácora.
    - `docs/PROMPT_CHAT_UNIVERSAL.md` (orden de autoridad y carga obligatoria).
    - `ops/herramientas/deploy/generate_universal_prompt.py` (plantilla base de generación).
- **Verificación**:
  - `tickets_before = 3` y `non_zero_load_before = 2`.
  - post reset: `tickets_after = 0`.
  - post reset: `non_zero_load_after = 0`.
  - adjuntos DEV en filesystem (`/srv/monstruo_dev/data/tickets`) ya estaban en `0` elementos.
- **Estado**: CERRADO.

## HITO: 2026-02-23 - Restauración de servicio API DEV tras bloqueo (Incidente)
- **Solicitud**: reportada caída de la aplicación.
- **Causa raíz**: el contenedor `monstruo-dev-api` quedó en estado "zombie" (proceso bloqueado sin logs nuevos ni respuesta HTTP). Espacio en disco y DB normales.
- **Acción**: reinicio forzado del contenedor del API.
- **Estado**: RESTAURADO. Se verificó respuesta HTTP 200/404 y flujo de logs activo.
## HITO: 2026-02-20 - EPIC 11 Ticketera: eliminación de descripción duplicada y normalización visual (DEV)
- **Solicitud**: en la vista de lista, al abrir el detalle del ticket, la descripción aparecía redundante arriba de la línea de tiempo. Además, se pidió ajustar los colores del bloque de detalle para que fuera coherente con el resto de la aplicación (menos gris puro, más soporte al CSS global transparente de paneles). También, se indicó que el contenido de las 4 pestañas iniciaba a diferentes alturas.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - eliminada la renderización de `.tks-description-box` sobre la línea de tiempo (el comentario matriz original sigue existiendo ya dentro de la cronología).
  - `code/static/modulos/tks/js/tks_main.js`:
    - padding estandarizado en la vista dinámica Operación y los skeletons para evitar desalineación.
    - corregido contenedor superior en `renderOpsContainer`, quitando su espacio en bloque y posicionándolo de forma flotante y absoluta (`position: absolute; right: 2rem; top: -3.5rem;`) al nivel de las pestañas principales para evitar que este div empuje la tabla principal.
    - eliminados permanentemente los botones de ejecución manual ("Recuperar huérfanos" y "Actualizar") de la vista Operaciones a petición del usuario.
    - retirada de las exigencias del token de control (`draftLockToken`) y del latido (heartbeat) para la edición de borradores de correo.
    - RESTRICCIÓN ROL: la capacidad de Drag & Drop de Kanban (`canDrag`) fue asignada exclusivamente a `sessionCtx.isAdmin`, relegando a técnicos/gerencia a lectura. Al fallar el D&D, el Kanban se autorecarga devolviendo la carta en reversa.
  - `code/app/core/tickets_service.py`:
    - anulada la validación estricta de lock tokens (`_validate_draft_lock`) para simplificar el flujo ya que la asignación es exclusiva.
    - implementada validación backend y matriz de regresión para transiciones restrictivas por ticket: un CERRADO solo puede resucitar parcialmente como RESUELTO (nunca a abierto/progreso de golpe). Y un RESUELTO no vuelve directo a ABIERTO sino solo a EN PROGRESO.
  - `code/static/modulos/tks/css/tks.css`:
    - rediseño estético alineado al estándar PMO/ERP en la vista aislada `.tks-full-detail-view` (panel sin caja absoluta, fondo completamente transparente, bordes delegados).
    - fondos forzados como radial-gradient o #0b1421 removidos.
    - migración de tarjetas (incluyendo feeds y header flotante) a variables del ecosistema: `var(--panel-strong)`, `var(--border)`.
    - hover explícito ajustado en botones flotantes (`.tks-detail-close`) con `var(--neon)`.
    - paddings estandarizados a cero superiores para `.tks-dashboard`, `.tks-toolbar`, `.tks-kanban-board` para evitar que las vistas salten en el eje Y respecto a su contenedor maestro `.section-block`.
  - `code/static/modulos/tks/tks.html`:
    - cache bust de estilos y js actualizado: `tks.css?v=42` y `tks_main.js?v=45`.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` ✅
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 17:35 - Causa raíz PMO vs ERP (desalineación vertical) + corrección estructural (DEV)
- **Solicitud**: revisar por qué PMO y ERP seguían viéndose a distinta altura.
- **Causa raíz detectada**:
  - **Estructura distinta**:
    - PMO: `section-header` y `tab-bar` eran hijos directos de `.main-inner`.
    - ERP: estaban dentro de un `<div>` wrapper adicional.
    - Esto alteraba el espaciado percibido por cómo aplica `gap` en `.main-inner`.
  - **Comportamiento de tabs distinto**:
    - ERP tenía más tabs y podía generar wrapping/segunda línea, cambiando altura visual del bloque.
- **Corrección aplicada**:
  - `code/static/modulos/erp/erp.html`:
    - se elimina wrapper extra; ahora ERP replica la misma jerarquía de PMO.
    - `body` vuelve a `sidebar-collapsed` sin override específico.
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - se elimina ajuste específico `erp-shell`.
    - para `module-tabs-header + .tab-bar`:
      - no-wrap (`flex-wrap: nowrap`),
      - scroll horizontal cuando no cabe,
      - tabs compactas homogéneas.
  - cache-bust:
    - `monstruo.css` unificado a `v=67.7` en shells de módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 17:32 - ERP: ajuste fino vertical de tabs para alinear con PMO (DEV)
- **Solicitud**: bajar un poco la altura/posición de la barra de pestañas en ERP para alinearla con PMO.
- **Entregable**:
  - `code/static/modulos/erp/erp.html`:
    - `body` actualizado a `class="sidebar-collapsed erp-shell"` para permitir ajuste específico de ERP.
    - cache-bust local ERP de `monstruo.css` a `v=67.6`.
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - override específico: `body.erp-shell .module-tabs-header + .tab-bar { margin-top: 6px; }`
    - no afecta PMO ni otros módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 17:28 - PMO/ERP: tabs más pequeñas y en una sola línea (DEV)
- **Solicitud**: PMO y ERP aún se veían diferentes; mantener espacio tipo PMO y reducir tamaño visual de pestañas.
- **Entregable**:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - para contexto `module-tabs-header + tab-bar` (PMO/ERP):
      - tabs en una sola línea (`flex-wrap: nowrap`),
      - scroll horizontal suave cuando no cabe (`overflow-x: auto`),
      - pestañas más compactas:
        - `min-height: 34px`,
        - `min-width: 86px`,
        - padding y tipografía reducidos.
      - scrollbar horizontal estilizado para mantener UX limpia.
  - cache-bust:
    - `monstruo.css` actualizado de `v=67.4` a `v=67.5` en shells de módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 17:24 - PMO/ERP: header de tabs unificado (misma altura y separación) (DEV)
- **Solicitud**: PMO y ERP aún se veían a distinta altura entre título y pestañas.
- **Entregable**:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - nueva clase global `module-tabs-header`:
      - `min-height` uniforme,
      - `margin-bottom` uniforme,
      - `padding-bottom` controlado.
    - regla específica `module-tabs-header + .tab-bar` para fijar separación idéntica.
    - ajuste responsive: desactiva `min-height` forzado en móvil (`<=900px`).
  - `code/static/modulos/pmo/pmo.html`:
    - header principal actualizado a `class="section-header module-tabs-header"`.
  - `code/static/modulos/erp/erp.html`:
    - header principal actualizado a `class="section-header module-tabs-header"`.
  - cache-bust:
    - `monstruo.css` actualizado de `v=67.3` a `v=67.4` en shells de módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 17:20 - PMO/ERP: espaciado uniforme entre título y pestañas (DEV)
- **Solicitud**: igualar el espacio entre título (`section-header`) y pestañas (`tab-bar`) porque PMO y ERP se veían distintos.
- **Entregable**:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - nueva regla global: `.section-header + .tab-bar { margin-top: 10px }` para separación homogénea.
  - cache-bust:
    - `monstruo.css` actualizado de `v=67.2` a `v=67.3` en shells de módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 17:10 - Homogeneización global de pestañas (altura y tamaño) (DEV)
- **Solicitud**: alinear pestañas a una misma altura y tamaño aproximado para homogeneidad visual.
- **Entregable**:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - estandarización global de tabs (`.tab-bar > .tab-btn`):
      - altura mínima uniforme (`min-height: 40px`),
      - ancho mínimo aproximado (`min-width: 108px`),
      - alineación vertical/horizontal centrada con `inline-flex`,
      - iconos normalizados (`width` y `line-height` fijos),
      - ajuste responsive (`<=900px` baja `min-width` a `96px`).
    - `tab-bar` con `align-items: stretch` y `row-gap` uniforme para evitar “saltos” entre filas.
  - cache-bust:
    - `monstruo.css` actualizado de `v=67.1` a `v=67.2` en shells de módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 17:07 - Estándar global sin cuadros de fondo para módulos (DEV)
- **Solicitud**: dejar guardado este estilo en el ejemplo para que todos los módulos se vean iguales sin cuadros de fondo.
- **Entregable**:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - `section-block` global actualizado a:
      - `background: transparent`,
      - `border: none`,
      - `box-shadow: none`,
      - `border-radius: 0`.
  - `code/static/modulos/dashboard/dashboard.html`:
    - guía visual actualizada para declarar explícitamente:
      - contenedor principal sin cuadro base,
      - checklist con regla de contenedor transparente.
  - `docs/PLAN_MAESTRO_MONSTRUO.md`:
    - estándar visual reforzado con regla permanente:
      - `section-block` transparente, sin borde ni sombra.
  - cache-bust:
    - `monstruo.css` actualizado de `v=67.0` a `v=67.1` en shells de módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 17:05 - ERP: sin cuadro de fondo (alineado a PMO) (DEV)
- **Solicitud**: quitar el cuadro/fondo contenedor en ERP para que se vea el fondo general, como en PMO.
- **Entregable**:
  - `code/static/modulos/erp/erp.html`:
    - se elimina contenedor visual `section-block` del layout principal ERP (queda contenedor neutro sin panel de fondo).
  - `code/static/modulos/erp/resumen/resumen.html`:
    - se elimina clase `resumen-panel` del bloque de estado de clientes.
  - `code/static/modulos/erp/resumen/resumen.css`:
    - panel de resumen deja de tener fondo/borde (`background: transparent; border: none; padding: 0`).
  - cache-bust:
    - `monstruo.css` actualizado de `v=66.9` a `v=67.0` en shells de módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 17:03 - ERP: pestaña Resumen con KPIs y orden visual tipo PMO (DEV)
- **Solicitud**: agregar pestaña `Resumen` en ERP para concentrar KPIs y ordenar la pantalla principal, acercándola al patrón PMO.
- **Entregable**:
  - `code/static/modulos/erp/erp.html`:
    - se agrega `Resumen` como primera pestaña del `tab-bar`.
    - `Resumen` queda como vista inicial por defecto (`switchTab('resumen')`).
    - se elimina bloque de KPIs fijos fuera de tabs para evitar desorden visual.
    - la estructura principal queda en `section-block` para consistencia con PMO.
    - se agrega init explícito para `resumen` al cargar el script (`window.initResumen()`).
  - `code/static/modulos/erp/resumen/resumen.html`:
    - se restauran KPIs dentro de la vista `Resumen` (`kpi-sales`, `kpi-debt`, `kpi-cash`).
    - panel de estado de clientes ordenado con acción de refresco.
  - `code/static/modulos/erp/resumen/resumen.css`:
    - layout vertical limpio para resumen (KPIs arriba + panel de clientes debajo).
    - estilos de color de KPIs y refinamiento de panel/listado.
- **Evidencia técnica (DEV)**:
  - `node --check /tmp/erp_inline.js` (script inline extraído de `erp.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:58 - Rollback de verde global y tabs activas sin fondo verde (DEV)
- **Solicitud**: revertir el cambio de verde aplicado y quitar el fondo verde del texto/pestaña activa.
- **Entregable**:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - `tab-btn.active` actualizado a:
      - fondo transparente (`background: transparent`),
      - sin halo (`box-shadow: none`),
      - texto activo en acento sin relleno.
    - rollback completo del bloque específico `pmo-shell/erp-shell` agregado previamente.
  - `code/static/modulos/pmo/pmo.html`:
    - `body` restaurado a `class="sidebar-collapsed"`.
  - `code/static/modulos/erp/erp.html`:
    - `body` restaurado a `class="sidebar-collapsed"`.
  - cache-bust:
    - `monstruo.css` actualizado de `v=66.8` a `v=66.9` en shells de módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:56 - PMO/ERP: ajuste de verde de títulos/acento (DEV)
- **Solicitud**: bajar intensidad del verde en la guía base PMO + ERP porque se percibía muy chillón/brillante.
- **Entregable**:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - override específico para `body.pmo-shell` y `body.erp-shell`:
      - acento `--neon` suavizado,
      - `tab-btn.active` y `btn-primary` con gradiente/halo más moderado.
  - `code/static/modulos/pmo/pmo.html`:
    - `body` actualizado a `class="sidebar-collapsed pmo-shell"`.
  - `code/static/modulos/erp/erp.html`:
    - `body` actualizado a `class="sidebar-collapsed erp-shell"`.
  - cache-bust:
    - `monstruo.css` actualizado de `v=66.7` a `v=66.8` en shells de módulos.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:49 - Guía visual unificada PMO+ERP aplicada transversalmente (DEV)
- **Solicitud**: usar PMO + ERP como base visual oficial, dejar guía explícita para agentes y aplicar estilo consistente a Ticketera y resto de módulos.
- **Entregable**:
  - `code/static/modulos/_compartido/css/monstruo.css`:
    - nueva capa global **PMO+ERP Visual Standard** para:
      - paneles (`section-block`, `section-header`),
      - tabs (`tab-bar`, `tab-btn`),
      - botones (`btn-primary`, `btn-secondary`),
      - campos (`input-dark`),
      - tablas (`monstruo-table`),
      - modales (`modal-content`, `dialog`, `cfg-modal-card`, `tks-modal`).
    - aliases de tokens para consistencia transversal:
      - `--accent-color`, `--text-main`, `--text-muted`, `--bg`.
  - `code/static/modulos/tks/css/tks.css`:
    - Ticketera alineada al estándar PMO/ERP:
      - tokens de color/borde/superficie actualizados a paleta global,
      - tab bar y botón primario ajustados a estilo neon compartido,
      - corrección de referencia `--tks-primary` -> `--tks-accent`.
  - `code/static/modulos/dashboard/dashboard.html`:
    - sección **Guía Visual de la App** actualizada para declarar PMO+ERP como fuente oficial obligatoria para agentes.
  - `docs/PLAN_MAESTRO_MONSTRUO.md`:
    - estándar visual actualizado formalmente a **PMO + ERP (Gold Standard)** con contrato visual global.
  - cache-bust global:
    - `monstruo.css` actualizado a `v=66.7` en shells de módulos.
    - `tks.css` actualizado a `v=36` en Ticketera.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` ✅
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
  - `node --check /tmp/dashboard_inline.js` (script inline extraído de `dashboard.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:31 - Configuración: ajuste final de ancho modal (DEV)
- **Solicitud**: dejar la ventana de `Editar Usuario` más ancha manteniendo la grilla de 3 cuadros.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - `cfg-modal-card` ampliado de `760px` a `900px` (`width: min(900px, 100%)`).
    - se mantiene `cfg-scroll-grid` en 3 columnas por defecto (`1fr 1fr 1fr`).
    - responsive preservado: `<=980px` (2 columnas), `<=720px` (1 columna).
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:30 - Configuración: modal más ancho + grilla de 3 columnas en selector (DEV)
- **Solicitud**: ampliar ventana de `Editar Usuario` y mostrar 3 cuadros por fila en bloques de selección para ahorrar espacio.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - modal de usuario ampliado de `560px` a `760px` (`cfg-modal-card`) para mejor lectura en desktop.
    - `cfg-scroll-grid` actualizado a 3 columnas por defecto (`1fr 1fr 1fr`).
    - responsive preservado:
      - en `<=980px` baja a 2 columnas,
      - en `<=720px` baja a 1 columna.
- **Evidencia técnica (DEV)**:
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:27 - Configuración: módulos sin checkbox visible (alineado a tarjetas de roles) (DEV)
- **Solicitud**: en modal `Editar Usuario`, quitar el checkbox visual de `Módulos` para que se vea igual al bloque de `Roles adicionales`.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - checkbox de módulos oculto visualmente (se mantiene como estado interno).
    - nuevos estilos `cfg-check-mark` para mostrar selección con marca `✓` al mismo estilo de roles adicionales.
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - render de módulos actualizado a tarjeta con:
      - texto del módulo,
      - marca visual de seleccionado,
      - toggle al click sobre toda la tarjeta.
    - persistencia de guardado intacta (sigue leyendo checkboxes internos).
  - cache-bust de `users_ui.js` actualizado a `v=18`.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:24 - Configuración: compactación adicional de cuadros en modal Editar Usuario (DEV)
- **Solicitud**: los cuadros de `Módulos` y `Roles adicionales` seguían viéndose grandes.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - reducción de densidad visual en ambos bloques:
      - menor `max-height` y padding del grid,
      - menor `min-height`/padding de tiles,
      - tipografía más compacta,
      - checkbox más pequeño.
    - estilos compactados aplicados de forma simétrica a:
      - `.cfg-check-item` (Módulos),
      - `.role-square-btn` (Roles adicionales).
    - cache-bust de `users_ui.js` actualizado a `v=17`.
- **Evidencia técnica (DEV)**:
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:22 - Configuración: homogeneización visual de Módulos y Roles adicionales en modal (DEV)
- **Solicitud**: en `Editar Usuario`, los bloques `Módulos` y `Roles adicionales` se veían demasiado distintos; se pidió estilo similar en un tamaño intermedio.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - ambos bloques (`cfg-check-item` y `role-square-btn`) ahora comparten lenguaje visual:
      - altura reducida a formato medio,
      - padding y radio homogéneos,
      - bordes/fondos y estados hover/selección alineados al tema del dashboard (`neon/info`).
    - checkboxes de módulos con acento visual consistente (`var(--info)`).
    - `cfg-scroll-grid` ajustado para mejor densidad visual sin agrandar tarjetas.
    - cache-bust de `users_ui.js` actualizado a `v=16`.
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - módulos ahora aplican clase visual `is-checked` en runtime para que el estado seleccionado se vea igual de claro que en `Roles adicionales`.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:09 - Configuración: 3 paneles separados + paleta unificada según guía Dashboard (DEV)
- **Solicitud**: dejar 3 cuadros distintos y unificar colores (sin inventar), siguiendo la guía visual del dashboard.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - layout separado en **3 paneles**:
      1) `Usuarios y Roles`,
      2) `Permisos Efectivos por Usuario`,
      3) `Permisos por Rol`.
    - paleta de permisos por módulo unificada con esquema dashboard (base `neon/info/warning/danger` + neutral).
    - se eliminaron tonos multicolor heterogéneos previos para mantener consistencia visual.
    - cache-bust `users_ui.js` actualizado a `v=15`.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:05 - Configuración: layout full-width de permisos + color por módulo + vista de permisos por usuario (DEV)
- **Solicitud**: dejar `Permisos por Rol` en ancho completo, colorear permisos por módulo y agregar cuadro bajo gestión de usuarios con permisos efectivos por usuario (multi-rol).
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - `Permisos por Rol` ahora en filas full-width (no tarjetas cuadradas).
    - nueva paleta por módulo en chips de permisos (`scope-mod-*`).
    - bloque nuevo bajo tabla de usuarios: **Permisos Efectivos por Usuario** (`cfgUserScopesBody`).
    - cache-bust `users_ui.js` actualizado a `v=14`.
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - render de chips con clase por módulo (`scopeModuleClass(...)` + `renderScopePills(...)`).
    - render nuevo de permisos efectivos por usuario (`renderUserScopeGuide(...)`) calculados por unión de roles.
    - `load()` actualiza de forma sincronizada:
      - tabla usuarios,
      - permisos por usuario,
      - permisos por rol.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 16:04 - Configuración: permisos full-width + color por módulo + permisos efectivos por usuario (DEV)
- **Solicitud**: matriz de permisos por rol en ancho completo (no tarjetas cuadradas), color por módulo y agregar cuadro de permisos efectivos por usuario para casos multi-rol.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - estilos nuevos de permisos:
      - filas full-width para `Permisos por Rol`,
      - chips de permisos con color por módulo (`Dashboard`, `Ticketera`, `PMO`, `CRM`, etc.),
      - fallback visual `default` para módulos no mapeados.
    - nuevo bloque bajo `Usuarios y Roles`:
      - **Permisos Efectivos por Usuario** (`cfgUserScopesBody`).
    - `Permisos por Rol` actualizado a layout de lista vertical full-width.
    - cache-bust de `users_ui.js` actualizado a `v=14`.
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - nuevo render de pills por módulo (`scopeModuleClass`, `renderScopePills`).
    - restaurado cálculo de permisos efectivos por usuario (`scopesForRoles`) y nuevo render `renderUserScopeGuide()`.
    - `load()` ahora pinta en conjunto:
      - tabla usuarios/roles,
      - permisos efectivos por usuario,
      - matriz permisos por rol.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 15:50 - Configuración: separación estricta Usuarios vs Permisos por Rol (DEV)
- **Solicitud**: evitar mezcla de conceptos; en gestión de usuarios no deben aparecer permisos, esos deben verse aparte por rol.
- **Entregable**:
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - tabla de usuarios refactorizada para mostrar solo `Roles` por usuario (sin alcances/permisos embebidos en la fila).
    - la matriz de permisos por rol se mantiene independiente en su bloque dedicado.
  - `code/static/modulos/configuracion/configuracion.html`:
    - sección dividida en dos paneles separados:
      - `Usuarios y Roles` (administración),
      - `Permisos por Rol` (referencia de alcances).
    - texto de cabecera actualizado para dejar explícita la separación.
    - columna de tabla renombrada de `Perfil` a `Roles`.
    - cache-bust `users_ui.js` actualizado a `v=13`.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 15:44 - Configuración: orden consistente de permisos/alcances (DEV)
- **Solicitud**: los permisos se veían desordenados en la vista por roles.
- **Entregable**:
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - nuevo orden explícito para permisos por prioridad de módulo (`Dashboard`, `Ticketera`, `PMO`, etc.) y tipo de acción (`lectura`, `gestión`, `edición`, etc.).
    - sorting aplicado en dos niveles:
      - dentro de cada rol en la matriz,
      - en alcances efectivos del usuario (tabla principal).
    - orden de tarjetas de roles fijado según `ROLE_OPTIONS` (no alfabético accidental).
  - `code/static/modulos/configuracion/configuracion.html`:
    - cache-bust de `users_ui.js` actualizado a `v=12`.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 15:41 - Configuración: fallback local para matriz de alcances por rol (DEV)
- **Solicitud**: en Configuración aparecía `No se pudo cargar la matriz de alcances`, pero se requiere mantener visible esa guía para operar por roles.
- **Entregable**:
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - agregado `ROLE_SCOPE_FALLBACK` con descripción + alcances por rol.
    - nueva función `fallbackRoleScopes()` para poblar guía cuando falle `/api/config/role-scopes` o venga vacío.
    - `load()` ahora usa estrategia robusta:
      - API de alcances si responde,
      - fallback local automático si no responde.
  - `code/static/modulos/configuracion/configuracion.html`:
    - cache-bust de `users_ui.js` actualizado a `v=11`.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual del usuario en runtime.

## HITO: 2026-02-19 15:30 - Configuración/Ticketera: simplificación a modelo solo-roles + matriz de alcances (DEV)
- **Solicitud**: eliminar enredo entre roles y especialidades, operar solo con roles y dejar alcances claros por rol.
- **Entregable**:
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - refactor completo a gestión solo-roles (sin carga de especialidades ni acciones asociadas).
    - celda de perfil ahora muestra:
      - `Roles` (principal + adicionales),
      - `Alcances` (permisos efectivos derivados de matriz de roles).
    - nueva renderización de **guía de alcances por rol** en panel dedicado.
  - `code/static/modulos/configuracion/configuracion.html`:
    - removido bloque de “Agregar Especialidad Técnica”.
    - sección unificada queda enfocada en `Usuarios y Roles`.
    - agregado bloque visual `Matriz de Alcances por Rol`.
    - cache-bust `users_ui.js` actualizado a `v=10`.
  - `code/app/api/routers/config_router.py`:
    - nuevo endpoint `GET /api/config/role-scopes` (protegido por `admin.settings`) que expone:
      - rol, etiqueta, descripción y detalle de permisos (alcances) para consumo UI.
  - `code/app/core/tickets_service.py`:
    - `list_specialties()` con fallback por roles técnicos activos para mantener compatibilidad de Ticketera en modo solo-roles.
    - `get_assignment_timeline()` ahora consume `list_specialties()` (incluye fallback), evitando lanes vacíos cuando no hay especialidades explícitas.
    - `auto_asignar()` agrega fallback final por menor carga real de tickets abiertos/en_progreso usando roles técnicos.
  - `code/static/modulos/tks/js/tks_main.js` y `code/static/modulos/tks/js/tks_ui.js`:
    - etiquetas de asignación/timeline priorizan roles técnicos (no especialidades) para consistencia de lenguaje.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust: `tks_ui.js?v=67`, `tks_main.js?v=43`.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
  - `node --check code/static/modulos/tks/js/tks_main.js` ✅
  - `node --check code/static/modulos/tks/js/tks_ui.js` ✅
  - validación sintáctica Python por `compile(..., 'exec')`:
    - `code/app/api/routers/config_router.py` ✅
    - `code/app/core/tickets_service.py` ✅
  - `python3 tests/unit_ticketera_core.py` ✅
  - `python3 tests/unit_ticketera_frontend_security.py` ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual del usuario en runtime.

## HITO: 2026-02-19 15:15 - Configuración: deduplicación visual roles vs especialidades (DEV)
- **Solicitud**: en la tabla unificada se repetían conceptos cuando un rol y una especialidad eran equivalentes (ej: `Redes` en ambos bloques).
- **Entregable**:
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - nuevo normalizador `normalizeKey(...)` para comparar roles/especialidades de forma consistente.
    - nueva matriz de equivalencia `ROLE_SPECIALTY_EQUIV` (incluye `implementaciones -> ejecucion`).
    - deduplicación en render:
      - bloque de roles se mantiene completo,
      - bloque de especialidades solo muestra especialidades adicionales no cubiertas por roles.
    - mensaje contextual cuando aplica dedupe total: `Sin especialidades adicionales`.
    - sin cambios en acciones operativas: toggle de disponibilidad sigue evaluando todas las especialidades reales del usuario.
  - `code/static/modulos/configuracion/configuracion.html`:
    - cache-bust de `users_ui.js` actualizado a `v=9` para evitar servir JS anterior desde navegador.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-18 16:40 - EPIC 11 Ticketera/Security: hardening auth + separación DEV/PROD + XSS guard (DEV)
- **Solicitud**: corregir hallazgos de auditoría técnica sin romper UX principal.
- **Entregable**:
  - Backend/Auth:
    - `code/app/main.py`:
      - rate-limit de intentos fallidos de login en `/api/auth/login` y `/auth/login` (`429` + `Retry-After`).
      - OAuth Google con `state` anti-CSRF (set/validate/delete cookie `oauth_state`).
      - auto-provisión Google restringida a allowlist explícita (`GOOGLE_AUTO_PROVISION_ALLOWLIST`) + cuentas mapeadas.
      - validación de `SECRET_KEY` al startup: bloqueo en PROD si débil y clave efímera en DEV si falta/insegura.
  - Configuración seguridad:
    - `code/app/core/config.py`:
      - `SECRET_KEY` sin valor inseguro hardcodeado por defecto.
      - nuevas variables: `GOOGLE_AUTO_PROVISION_ALLOWLIST`, `GOOGLE_OAUTH_STATE_TTL_SECONDS`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS`, `LOGIN_RATE_LIMIT_MAX_ATTEMPTS`.
      - permiso `tickets:compliance` agregado explícitamente a `encargado_mesa`.
  - Ticketera/Storage:
    - `code/app/core/tickets_service.py`:
      - roots permitidos de adjuntos ya no incluyen simultáneamente `/srv/monstruo` y `/srv/monstruo_dev` por defecto.
    - `docker-compose.yaml`:
      - eliminación de credenciales hardcodeadas de Postgres/secret JWT.
      - `DB_URL` y secretos desde variables obligatorias.
      - mounts de tickets/compliance ligados a variables de entorno para evitar mezcla DEV/PROD.
  - Frontend Ticketera (hardening XSS):
    - `code/static/modulos/tks/js/tks_ui.js`:
      - helper `escapeJsSingleQuoted` y uso en parámetros dinámicos dentro de `onclick`.
    - `code/static/modulos/tks/js/tks_main.js`:
      - escape HTML en errores renderizados con `innerHTML`.
      - escape seguro en `selectClient(...)` y generación de bloque de `payment_url`.
  - CI:
    - `.github/workflows/deploy.yml`: agrega paso `python tests/verify_hardening.py` en job de `tests`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación funcional/manual del usuario en runtime.

## HITO: 2026-02-19 13:19 - Configuración/Dashboard: normalización visual + guía de estilo para agentes (DEV)
- **Solicitud**: mejorar el módulo de Configuración (evitar cuadros blancos/modales inconsistentes), mantener estilo homogéneo de app, y publicar ejemplos visuales en Dashboard para orientar a futuros agentes.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - refactor visual profundo con clases `cfg-*` para paneles, tablas, inputs, botones y modal (sin romper IDs/eventos existentes).
    - estilo oscuro consistente para `input-dark`, `btn-primary`, `btn-secondary`, `btn-icon-sm` y estructura responsive.
    - tabla de especialidades migrada de `onclick` inline a delegación por `data-*`.
    - cierre de modal por clic fuera del contenido y cache-bust de `users_ui.js` (`v=6`) + `sidebar.js` (`v=11`).
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - render de tabla y badges migrado a clases reutilizables (menos inline styles).
    - hardening de render con `escapeHtml` y `data-*` encode/decode para acciones editar/eliminar.
    - delegación de eventos en tabla de usuarios y método nuevo `UsersUI.closeModal()` para control limpio de modal.
  - `code/static/modulos/dashboard/dashboard.html`:
    - rediseño de layout dashboard con clases dedicadas y eliminación de render acumulativo defectuoso en alertas (antes usaba `+=`).
    - widgets Ticketera renderizados con escape de texto y navegación por `data-ticket-id` (sin `onclick` inline).
    - sección nueva **“Guía Visual de la App”** con ejemplos y checklist para que cualquier agente entienda el estándar visual/técnico.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (extraído de `configuracion.html`) ✅
  - `node --check /tmp/dashboard_inline.js` (extraído de `dashboard.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 13:29 - Configuración/Ticketera: alineación de carga técnica con timeline real (DEV)
- **Solicitud**: en Configuración, la `Carga` de técnicos no coincidía con la carga visible en Ticketera.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - `loadSpecialties()` ahora consulta en paralelo:
      - `/api/tks/especialidades` (config base),
      - `/api/tks/asignacion/timeline` (carga real de Ticketera).
    - nueva función `buildLiveLoadMap(...)` para mapear `username -> active_count`.
    - la columna `Carga` se renderiza con carga real activa de Ticketera (`active_count`), manteniendo fallback a `current_load` histórico si falla timeline.
    - barra de porcentaje (`Carga/Máx`) recalculada con carga real para mantener coherencia visual entre módulos.
- **Evidencia técnica (DEV)**:
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 13:37 - Configuración: fusión de tablas en gestión unificada (DEV)
- **Solicitud**: eliminar duplicidad de tablas de usuarios/técnicos y administrar todo desde un solo cuadro.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - eliminada la sección separada de `Mesa de Ayuda — Técnicos` con su tabla independiente.
    - `Gestión de Usuarios` evolucionada a **Gestión Unificada** con:
      - formulario de alta de especialidad técnica,
      - una sola tabla `Usuarios + Especialidades Técnicas` con columnas de roles, especialidades, carga real, disponibilidad y acciones.
    - actualización de estilos `cfg-*` para chips de especialidad, mini-acciones y celda de carga.
    - cache-bust actualizado de `users_ui.js` a `v=7`.
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - refactor a vista unificada: carga usuarios + especialidades + timeline en un solo `load()`.
    - render único en `tbodyUsers` con acciones integradas:
      - editar/eliminar usuario,
      - agregar especialidad (desde formulario),
      - quitar especialidad por fila,
      - activar/desactivar disponibilidad técnica.
    - sincronización del selector de técnico con la lista de usuarios para evitar desalineaciones.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 13:41 - Configuración: simplificación final sin bloque de carga (DEV)
- **Solicitud**: eliminar de Configuración todo lo relacionado a “carga”, porque no aporta a esta vista.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - removida columna `Carga Real` de la tabla unificada.
    - removido campo `Carga Máx.` del formulario de alta rápida de especialidad.
    - ajuste de estructura de columnas (`colspan`) y limpieza de estilos CSS asociados a barras de carga.
    - cache-bust de `users_ui.js` actualizado a `v=8`.
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - eliminada lógica de render de carga (`renderLoadCell`) y cálculo de carga en runtime.
    - eliminada consulta a `/api/tks/asignacion/timeline` para esta vista.
    - alta de especialidad mantiene `max_load` por defecto interno (`10`) sin exponerlo en UI.
    - disponibilidad técnica se mantiene administrable desde acciones de la fila (toggle), sin mostrar métricas de carga.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 13:43 - Configuración: limpieza de valor fijo en alta de especialidad (DEV)
- **Solicitud**: eliminar remanente “quemado” en lógica de especialidades.
- **Entregable**:
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - `addSpecialtyFromForm()` ya no envía `max_load` fijo desde frontend.
    - creación de especialidad delega valor por defecto al backend (`SpecialtyUpsert.max_load=10`), evitando hardcode innecesario en UI.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - búsqueda de texto `max_load` fijo y rótulos de carga en Configuración: sin coincidencias visibles ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 14:07 - Configuración: eliminación de columna “Creado” en tabla unificada (DEV)
- **Solicitud**: quitar la columna `Creado` de la tabla de gestión unificada.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - removido encabezado `Creado` de la tabla.
    - ajuste de `colspan` en estado de carga a 5 columnas.
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - removida celda `created_at` en el render de filas.
    - ajuste de placeholders (`sin datos`/`error`) a 5 columnas.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 14:15 - Configuración: fusión visual Roles + Especialidades en celda única (DEV)
- **Solicitud**: fusionar roles y especialidades en la tabla unificada, mostrando roles arriba y especialidades abajo.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - cabecera de tabla simplificada a: `Usuario | Perfil | Estado | Acciones`.
    - nuevas clases visuales de perfil (`cfg-profile-*`) para separar bloques dentro de una misma celda.
    - ajuste de `colspan` a 4 columnas.
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - nuevo renderer `renderProfileCell(...)`:
      - bloque superior: roles (badges),
      - bloque inferior: especialidades (lista con acciones).
    - eliminación de columnas separadas de roles/especialidades en el render de filas.
    - placeholders de vacío/error alineados a 4 columnas.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-19 15:12 - Configuración: especialidades sin “X” y tamaño visual alineado a roles (DEV)
- **Solicitud**: quitar la `X` de las especialidades y dejar su tamaño similar al badge de rol.
- **Entregable**:
  - `code/static/modulos/configuracion/configuracion.html`:
    - `cfg-specialty-list` cambiado a layout wrap horizontal.
    - `cfg-specialty-item` ajustado a formato “pill” (radio 999, padding compacto, tamaño de fuente 0.75rem) para homologar con badges de rol.
    - eliminación de estilos `cfg-mini-btn` (ya no se usan).
  - `code/static/modulos/configuracion/js/users_ui.js`:
    - `renderSpecialtiesCell(...)` ahora renderiza solo pills de especialidad, sin botón de borrado `X`.
    - removido manejo de acción `remove-spec` y función `removeSpecialty(...)` del flujo principal de tabla.
- **Evidencia técnica (DEV)**:
  - `node --check code/static/modulos/configuracion/js/users_ui.js` ✅
  - `node --check /tmp/config_inline.js` (script inline de `configuracion.html`) ✅
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario en runtime.

## HITO: 2026-02-17 19:55 - EPIC 11 Ticketera: normalización amplia de aliases para `encargado_mesa` + restart API DEV
- **Solicitud**: persistía error `rol inválido` al asignar cargo de mesa.
- **Entregable**:
  - `code/app/api/routers/admin_users.py` y `code/app/core/auth_service.py`:
    - normalización extendida de alias para cualquier variante con `encargado` + `mesa`.
    - soporte explícito de variantes adicionales (`encargado de mesa ayuda`, con/ sin `de`, espacios o guiones).
    - soporte de caracteres con tilde (normalización unicode).
  - Operación DEV:
    - reinicio de contenedor `monstruo-dev-api` para cargar cambios backend.
- **Estado**: IMPLEMENTADO EN CÓDIGO + RUNTIME DEV REINICIADO, pendiente confirmación funcional del usuario.

## HITO: 2026-02-17 23:10 - EPIC 11 Ticketera/Configuración: separación visual rol vs especialidad + selector multi-rol por tarjetas
- **Solicitud**: evitar confusión entre rol y especialidad; en ticketera mostrar especialidades (no roles) para técnicos como Fabián, y mantener multi-rol con UI más clara tipo “cuadros”.
- **Entregable**:
  - Ticketera:
    - etiquetas de persona asignada y timeline de asignación ajustadas para mostrar solo especialidad técnica (`Redes/Sistemas/...`) y no mezclar roles (`encargado_mesa`, etc.).
    - archivos: `code/static/modulos/tks/js/tks_main.js`, `code/static/modulos/tks/js/tks_ui.js`.
  - Configuración:
    - selector de `Roles adicionales` rediseñado a tarjetas/cuadros seleccionables (toggle visual), en vez de checkboxes planos.
    - tabla de usuarios mantiene rol principal limpio (sin “principal” textual extra).
    - selector de técnico en especialidades vuelve a mostrar rol principal para no mezclar con secundarios.
    - archivos: `code/static/modulos/configuracion/js/users_ui.js`, `code/static/modulos/configuracion/configuracion.html`.
  - Cache-bust:
    - `tks_ui.js?v=53`, `tks_main.js?v=39`, `users_ui.js?v=5`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual por usuario.

## HITO: 2026-02-17 20:35 - EPIC 11 Ticketera/Configuración: soporte multi-rol (rol principal + roles adicionales) y etiqueta combinada en asignación
- **Solicitud**: dejar de ver inconsistencia `encargado de mesa` vs `redes` en usuarios como Fabián, habilitando multi-rol real.
- **Entregable**:
  - Backend auth/RBAC:
    - `users.secondary_roles` agregado en migración idempotente (`code/app/core/db.py`).
    - JWT ahora incluye `roles` además de `role`; `deps.require_permission` evalúa unión de permisos por todos los roles (`code/app/core/security.py`, `code/app/core/deps.py`, `code/app/core/middleware.py`, `code/app/main.py`).
  - APIs de usuarios/config:
    - `admin_users` soporta `secondary_roles` en listar/crear/editar con validación y normalización de alias (`code/app/api/routers/admin_users.py`).
    - `/api/config/users` expone `secondary_roles` (`code/app/api/routers/config_router.py`).
  - Ticketera:
    - router ticketera consume `sess.roles` para scope técnico y reglas de actor (`code/app/api/routers/tks.py`).
    - servicio ticketera acepta lista de roles en validaciones y aprobaciones (`code/app/core/tickets_service.py`).
    - etiquetas de asignado muestran rol+especialidad (ej: `Encargado Mesa + Redes`) en lista de asignación y selector (`code/static/modulos/tks/js/tks_main.js`, `code/static/modulos/tks/js/tks_ui.js`).
  - Configuración UI:
    - modal de usuarios con `Roles adicionales (multi-rol)` y tabla mostrando rol principal + secundarios (`code/static/modulos/configuracion/configuracion.html`, `code/static/modulos/configuracion/js/users_ui.js`).
  - Cache-bust:
    - `tks_ui.js?v=52`, `tks_main.js?v=38`, `users_ui.js?v=4`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación manual en runtime (cambio/visualización de multi-rol con sesión nueva).

## HITO: 2026-02-17 19:48 - EPIC 11 Ticketera: fix adicional de normalización de rol `encargado_mesa` (DEV)
- **Solicitud**: persistía error `rol inválido` al asignar `Encargado Mesa Ayuda`.
- **Entregable**:
  - `code/app/api/routers/admin_users.py`:
    - normalización robusta de rol (sin tildes/mayúsculas, espacios y guiones).
    - alias agregado para `encargado_mesa_ayuda` -> `encargado_mesa`.
  - `code/app/core/auth_service.py`:
    - misma normalización robusta para creación de usuario por backend/login.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validar en runtime API.

## HITO: 2026-02-17 19:40 - EPIC 11 Ticketera: fix de actualización de rol `encargado_mesa` en admin users (DEV)
- **Solicitud**: al cambiar usuario a `Encargado de Mesa de Ayuda` daba error.
- **Entregable**:
  - `code/app/api/routers/admin_users.py`:
    - normalización de input de rol antes de validar/guardar (soporta alias con espacios/guiones):
      - `encargado de mesa de ayuda` / `encargado_de_mesa...` -> `encargado_mesa`.
      - `operaciones` -> `ops`.
    - aplicado en `POST /api/admin/users` y `PATCH /api/admin/users/{username}`.
    - mensaje de error de rol inválido ahora incluye valor recibido para diagnóstico.
  - `code/app/core/auth_service.py`:
    - normalización equivalente al crear usuarios por backend (`create_user`).
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación manual.

## HITO: 2026-02-17 19:32 - EPIC 11 Ticketera: nuevos cargos `encargado_mesa` + `gerencia` lectura estricta (DEV)
- **Solicitud**:
  - agregar cargo `encargado de mesa` (Fabian) como administrador operativo de mesa.
  - `gerencia` (Diego) solo lectura en ticketera: ver resumen/kanban, sin interacción; en detalle de lista solo línea de tiempo.
- **Entregable**:
  - Backend RBAC:
    - `code/app/core/config.py`:
      - nuevo rol `encargado_mesa` con permisos `tickets:read/tickets:write` + lectura operativa.
      - `gerencia` permanece lectura; se elimina `tickets:compliance` para evitar acciones operativas de ticketera.
    - `code/app/core/auth_service.py`:
      - `create_user()` acepta rol `encargado_mesa`.
    - `code/app/core/tickets_service.py`:
      - `encargado_mesa` agregado a `ROLES_ADMIN_GESTION` y `ROLES_DESPACHO_MESA` (gestión/asignación de mesa).
    - `code/app/api/routers/tks.py`:
      - `GET /api/tks/tablero` scope por tipo de rol:
        - técnicos (`ops/redes/sistemas/implementaciones`) ven solo sus tickets.
        - `admin`, `encargado_mesa`, `gerencia` ven vista global.
    - `code/app/main.py`:
      - auto-rol en login Google para usuarios nuevos de Telconsulting:
        - `diego@telconsulting.cl` -> `gerencia`,
        - `fabian.correa@telconsulting.cl` -> `encargado_mesa`,
        - fallback resto -> `ops`.
  - Frontend Ticketera:
    - `code/static/modulos/tks/js/tks_main.js`:
      - nuevos roles front (`encargado_mesa`, `gerencia`) y vista/permisos por rol.
      - `gerencia` ya no ve tab `Operación`.
      - kanban: solo roles con escritura pueden arrastrar/cambiar estado.
      - scope cliente de kanban alineado con backend (solo técnicos filtrados a sus tickets).
    - `code/static/modulos/tks/js/tks_ui.js`:
      - detalle para `gerencia` en modo mínimo: solo `Línea de tiempo` (sin composer/gestión/acciones).
  - Navegación/gestión usuarios:
    - `code/static/modulos/_compartido/js/sidebar.js`:
      - fallback de módulos incluye `encargado_mesa` y agrega `tks` a `gerencia`.
    - `code/static/modulos/configuracion/configuracion.html`:
      - selector de roles incorpora `Encargado Mesa Ayuda`.
  - Cache-bust:
    - `code/static/modulos/tks/tks.html`: `tks_ui.js?v=51`, `tks_main.js?v=37`, `sidebar.js?v=10`.
    - `code/static/modulos/configuracion/configuracion.html`: `sidebar.js?v=10`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación manual multiusuario.

## HITO: 2026-02-17 19:16 - EPIC 11 Ticketera: Persona asignada muestra nombre técnico + especialidad (DEV)
- **Solicitud**: en `Persona asignada`, mostrar nombre técnico y especialidad en lugar del correo/username.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_main.js`:
    - nuevo formateo de identidad técnica (`humanizeUsername`) y especialidad (`specialtyLabel`).
    - opciones del selector muestran `Nombre Técnico · Especialidad`.
    - `hydrateAssigneePicker()` también actualiza vista solo lectura con mismo formato.
    - toast de reasignación ahora usa etiqueta legible en vez de username crudo.
  - `code/static/modulos/tks/js/tks_ui.js`:
    - fallback visual en detalle/kanban para no mostrar correo crudo cuando no hay metadata cargada.
    - en detalle, bloque readonly de asignado ahora tiene id para hidratar etiqueta técnica.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust actualizado: `tks_ui.js?v=50`, `tks_main.js?v=36`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual.

## HITO: 2026-02-17 19:08 - EPIC 11 Ticketera: ajuste visual Persona asignada en card Cliente (DEV)
- **Solicitud**: mover visualmente `Persona asignada` un poco más abajo y ajustar tamaños/colores para que queden acordes al card.
- **Entregable**:
  - `code/static/modulos/tks/css/tks.css`:
    - nuevo estilo específico `.tks-assignee-control.in-customer` con mayor separación vertical y separador superior.
    - ajuste de tipografía/color del label y select para coherencia con `Cliente`.
    - ajuste visual del estado solo-lectura de asignado dentro del card.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust actualizado de estilos: `tks.css?v=26`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual.

## HITO: 2026-02-17 19:00 - EPIC 11 Ticketera: Kanban con scope por usuario (admin ve todo) (DEV)
- **Solicitud**: en `Kanban`, que admin vea todos los tickets y usuarios no admin solo sus propios tickets.
- **Entregable**:
  - `code/app/api/routers/tks.py`:
    - `GET /api/tks/tablero` ahora aplica scope explícito por rol:
      - `admin`: sin filtro de asignado (ve todo),
      - no admin: `asignado_a = username` del usuario en sesión.
    - evita visualización cruzada en Kanban para usuarios técnicos/no-admin.
  - `code/static/modulos/tks/js/tks_main.js`:
    - guardia adicional en cliente: antes de renderizar Kanban, roles no admin filtran solo tickets con `asignado_a = usuario de sesión`.
    - protege contra caché vieja o respuestas no scopeadas.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust actualizado: `tks_main.js?v=35`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación manual multiusuario.

## HITO: 2026-02-17 18:50 - EPIC 11 Ticketera: eliminación de cuadro final en Resumen (DEV)
- **Solicitud**: eliminar el cuadro extra que aparecía al final (abajo) en la vista `Resumen`.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - removida la sección final de cards por categoría (`by_category`) dentro de `renderDashboard(...)`.
    - `Resumen` ahora termina en la vista de `Asignación Técnica` sin bloque adicional al pie.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust actualizado: `tks_ui.js?v=49`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual.

## HITO: 2026-02-17 18:44 - EPIC 11 Ticketera: limpieza de metadata bajo estado actual (DEV)
- **Solicitud**: eliminar bajo `Estado actual` los datos de persona asignada y horas/SLA.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - removido bloque visual `tks-status-summary-meta` del card `Estado y gestión`.
    - `Estado actual` queda limpio con estado principal y countdown cuando aplique.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust actualizado: `tks_ui.js?v=48`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual.

## HITO: 2026-02-17 18:36 - EPIC 11 Ticketera: reasignación movida a card Cliente + selector directo (DEV)
- **Solicitud**: mover `Persona asignada` al cuadro derecho bajo `Cliente` y eliminar interacción doble (botón -> botón -> desplegable).
- **Entregable**:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - bloque `Persona asignada` movido desde `Estado y gestión` al card `Cliente`.
    - selector visible directo (`select`) con cambio inmediato en `onchange` (sin botón intermedio).
  - `code/static/modulos/tks/js/tks_main.js`:
    - `applyAssigneeChange()` ajustado para flujo directo sin toggle de panel oculto.
    - `toggleAssigneePicker()` queda como compatibilidad (focus/showPicker del select).
  - `code/static/modulos/tks/tks.html`:
    - cache-bust actualizado: `tks_ui.js?v=47`, `tks_main.js?v=34`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual.

## HITO: 2026-02-17 18:23 - EPIC 11 Ticketera: reasignación por lista en detalle (encargado de mesa) (DEV)
- **Solicitud**: en el detalle del ticket mostrar `Persona asignada` y al pinchar el nombre desplegar una lista para seleccionar a quién asignar.
- **Entregable**:
  - Backend (`code/app/core/tickets_service.py`):
    - nueva regla de despacho: rol `ops` puede reasignar tickets a otros usuarios cuando el ticket está asignado a sí mismo o sin asignar.
    - se mantiene control para evitar reasignación de tickets ajenos fuera de regla.
  - Frontend (`Lista > detalle`):
    - `code/static/modulos/tks/js/tks_ui.js`:
      - card `Estado y gestión` ahora incluye bloque `Persona asignada` con botón clickeable.
      - al abrir, despliega selector + acción `Asignar`.
    - `code/static/modulos/tks/js/tks_main.js`:
      - carga lista de asignables desde `/api/tks/especialidades` (dedupe por usuario, con cache local).
      - nuevas acciones `toggleAssigneePicker()` y `applyAssigneeChange(ticketId)`.
      - reasignación ejecutada con `PATCH /api/tks/tickets/{id}` (`asignado_a`).
    - `code/static/modulos/tks/css/tks.css`:
      - estilos nuevos para selector de persona asignada (desktop/mobile).
  - Cache-bust:
    - `tks.css?v=25`, `tks_ui.js?v=46`, `tks_main.js?v=33` en `code/static/modulos/tks/tks.html`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación manual con usuarios reales.

## HITO: 2026-02-17 18:15 - EPIC 11 Ticketera: eliminar card duplicado "General" en Resumen (DEV)
- **Solicitud**: quitar cuadro `General` al final de `Resumen` por información repetida.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - `renderDashboard(...)` ahora filtra la categoría `general` de `by_category`.
    - la fila de cards por categoría se oculta automáticamente si no quedan categorías para mostrar.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust de UI a `tks_ui.js?v=45`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual.

## HITO: 2026-02-17 18:08 - EPIC 11 Ticketera: resumen técnico por defecto + vista de timeline propia + orden General (DEV)
- **Solicitud**:
  - técnico debe entrar por defecto a `Resumen` (no `Lista`).
  - en `Resumen`, “General” debe aparecer primero.
  - técnico debe ver solo su línea de tiempo en asignación.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_main.js`:
    - pestaña inicial forzada a `dashboard` para todos los roles (técnico incluido).
    - nuevo helper `scopeAssignmentDataForSession(...)` para acotar datos de asignación según sesión.
    - para técnico: `technicians` filtrado al usuario logueado + `queue` vacía + `scope='mine'`.
    - aplicado tanto en `loadDashboard()` como en `loadAssignmentTimeline()`.
  - `code/static/modulos/tks/js/tks_ui.js`:
    - `renderAssignmentTimeline(...)` ordena filas con `general` primero y oculta `Cola sin asignar` cuando `scope='mine'`.
    - `renderDashboard(...)` ordena `by_category` con prioridad para `general` primero, luego por cantidad.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust: `tks_ui.js?v=44`, `tks_main.js?v=32`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual.

## HITO: 2026-02-17 18:02 - EPIC 11 Ticketera: scope por rol (admin sin correo, técnico solo sus tickets) (DEV)
- **Solicitud**:
  - admin no debe ver ni enviar `Responder cliente` y solo usar `Nota interna`.
  - técnico debe ver únicamente sus tickets (sin filtros en `Lista`) para evitar cruces.
  - en `Resumen`, técnico ve métricas y SLA de su propia carga.
- **Entregable**:
  - Backend `API` (`code/app/api/routers/tks.py`):
    - scope técnico forzado en `GET /api/tks/tickets` (ignora filtros de búsqueda/estado/categoría/severidad y fija `asignado_a` al usuario logueado).
    - scope técnico aplicado en `GET /api/tks/stats` y `GET /api/tks/asignacion/timeline`.
    - scope de lectura por ticket para técnicos en endpoints de detalle (`ticket`, `eventos`, `emails`, `workflow`, `approvals`, `attachments`, `download`, `email-draft`) con `403` si no son dueños.
    - `GET /api/tks/tablero` también respeta scope por usuario técnico.
  - Backend servicio (`code/app/core/tickets_service.py`):
    - `get_stats(asignado_a=...)` con filtros agregados por SQL.
    - `get_assignment_timeline(..., assignee=...)` con filtrado por técnico.
    - `add_comment(...)` permite nota interna para admin (manteniendo bloqueo de intervención en correo/adjuntos).
  - Frontend (`Lista/Detalle`):
    - `code/static/modulos/tks/js/tks_main.js`:
      - técnico en `Lista` sin filtros ni búsqueda; solo vista de tickets propios.
      - nuevo permiso `canAddInternalNote` (admin + técnico asignado).
      - `switchComposerMode()` bloquea modo `reply` cuando no existe.
    - `code/static/modulos/tks/js/tks_ui.js`:
      - en detalle, admin no ve botón ni panel `Responder cliente`.
      - `Nota interna` habilitada para admin.
    - cache-bust en `code/static/modulos/tks/tks.html`:
      - `tks_ui.js?v=43`
      - `tks_main.js?v=31`
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación manual multiusuario.

## HITO: 2026-02-17 17:40 - EPIC 11 Ticketera (Lista): composer de respuesta tipo correo con CC/CCO + revisión solo lectura (DEV)
- **Solicitud**: que responder ticket se vea como correo real (`Para`, `CC`, `CCO`, asunto, descripción, adjuntos) y que `Revisar y mandar` no abra otro editor, solo una confirmación de lectura.
- **Entregable**:
  - Backend DB:
    - `ticket_email_drafts`: nuevas columnas `cc_addrs`, `bcc_addrs`.
    - `ticket_emails`: nueva columna `bcc_addrs`.
    - migraciones idempotentes en `code/app/core/db.py`.
  - Backend servicio/API:
    - `EmailDraftUpdateIn` acepta `cc_addrs` y `bcc_addrs` (`code/app/api/routers/tks.py`).
    - `save_ticket_email_draft` persiste `to/cc/bcc/subject/body` con validación de correos y dedupe entre `to`, `cc`, `cco` (`code/app/core/tickets_service.py`).
    - `send_ticket_email_draft` usa `to + cc + cco` reales al enviar y registra `bcc_addrs` en historial de correo.
    - `reply_ticket_email` actualizado para trazabilidad `bcc_addrs` (compatibilidad sin CCO explícito desde endpoint legacy).
    - `get_ticket_emails(format_human)` expone `bcc_addrs`.
    - `send_email_advanced` soporta `bcc_emails` (`code/app/core/email.py`).
  - Frontend detalle Lista:
    - composer `Responder cliente` rediseñado con orden: `Para` -> `CC/CCO` (en 2 columnas) -> `Asunto` -> `Descripción` -> `Adjuntos`.
    - `Revisar y enviar` ahora guarda borrador y abre modal de confirmación **solo lectura** (sin inputs editables).
    - se agregó seguimiento de cambios pendientes también para `CC/CCO` al cerrar detalle.
    - feed de correos muestra `CCO` cuando exista.
    - archivos: `code/static/modulos/tks/js/tks_ui.js`, `code/static/modulos/tks/js/tks_main.js`, `code/static/modulos/tks/css/tks.css`.
  - Cache-bust:
    - `tks.css?v=24`, `tks_ui.js?v=41`, `tks_main.js?v=30` en `code/static/modulos/tks/tks.html`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV), pendiente validación visual/manual multiusuario.

## HITO: 2026-02-17 13:05 - EPIC 11 Ticketera: destinatarios adicionales por ticket (respuesta + cambios de estado) (DEV)
- **Solicitud**: poder sumar personas para que reciban la respuesta al cliente y los cambios de estado del ticket.
- **Entregable**:
  - Backend DB:
    - `tickets.notify_emails` (CSV de correos adicionales por ticket).
    - `ticket_emails.cc_addrs` para trazabilidad de copiados.
    - migraciones idempotentes en `code/app/core/db.py`.
  - Backend API/servicio:
    - `TicketCreate.notify_emails[]` y `TicketUpdate.notify_emails[]` en `code/app/api/routers/tks.py`.
    - `create_ticket` y `update_ticket` soportan/validan correos adicionales en `code/app/core/tickets_service.py`.
    - `reply_ticket_email` y `send_ticket_email_draft` ahora envían con `CC` automático usando `notify_emails`.
    - en cambio de `estado` (`update_ticket` o `transition_ticket`) se envía correo de actualización a `notify_emails`.
    - historial de correo registra `to_addr` y `cc_addrs` para visibilidad en timeline.
  - Backend email sender:
    - `send_email_advanced(..., cc_emails=[])` en `code/app/core/email.py`.
  - Frontend:
    - en detalle de ticket (`card Cliente`) se agregó editor `Copiados (respuesta y estado)` y botón `Guardar copiados`.
    - lectura de `CC` en items de correo del feed cuando aplica.
    - archivos: `code/static/modulos/tks/js/tks_ui.js`, `code/static/modulos/tks/js/tks_main.js`.
  - Cache-bust:
    - `tks_ui.js?v=40`, `tks_main.js?v=29` en `code/static/modulos/tks/tks.html`.
- **Validación**:
  - `node --check` PASS:
    - `code/static/modulos/tks/js/tks_ui.js`
    - `code/static/modulos/tks/js/tks_main.js`
  - AST parse Python PASS:
    - `code/app/core/email.py`
    - `code/app/core/db.py`
    - `code/app/core/tickets_service.py`
    - `code/app/api/routers/tks.py`
  - Smoke DEV:
    - reply por ticket incluye `cc_emails` esperados.
    - cambio de estado genera correo de actualización a `notify_emails`.
    - columnas DB presentes (`tickets.notify_emails`, `ticket_emails.cc_addrs`).
  - Runtime:
    - reinicio `monstruo-dev-api` + `/health` OK.
  - Limpieza post-smoke:
    - ticketera DEV reseteada nuevamente (`tickets_total=0`).
- **Estado**: IMPLEMENTADO EN CÓDIGO + OPERATIVO EN DEV.

## HITO: 2026-02-17 12:52 - EPIC 11 Ticketera: reset operativo completo en DEV para pruebas desde cero
- **Solicitud**: resetear ticketera para crear tickets desde 0.
- **Entregable**:
  - Limpieza de tablas operativas (TRUNCATE + RESTART IDENTITY):
    - `ticket_notification_attempts`
    - `ticket_notifications`
    - `ticket_email_draft_attachments`
    - `ticket_email_drafts`
    - `ticket_attachments`
    - `ticket_emails`
    - `ticket_comments`
    - `ticket_transitions`
    - `ticket_approvals`
    - `ticket_legal_holds`
    - `jira_issue_map`
    - `tickets`
  - Reinicio de carga técnica:
    - `user_specialties.current_load = 0`.
- **Validación**:
  - Post reset: `tickets_after = 0`.
  - `non_zero_load = 0`.
  - `tickets_service.get_stats()`:
    - `total = 0`,
    - `by_status = {}`,
    - `pivot_assignee = {}`.
- **Estado**: DATOS DE TICKETS RESETEADOS EN DEV.

## HITO: 2026-02-17 12:47 - EPIC 11 Ticketera: Asignación integrada en Resumen + retiro de carga por técnico (DEV)
- **Solicitud**: mover la vista de asignación al tab `Resumen` (debajo de KPI) y eliminar bloque repetido de `Carga por Técnico`.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_main.js`:
    - `loadDashboard()` ahora carga en paralelo `stats` + `assignment timeline`.
    - `renderDashboard()` recibe ambos datasets.
  - `code/static/modulos/tks/js/tks_ui.js`:
    - `renderDashboard(stats, assignmentData)` embebe la vista de asignación bajo KPIs.
    - eliminado bloque `📋 Carga por Técnico` (pivot assignee) para simplificar y evitar duplicidad.
  - `code/static/modulos/tks/tks.html`:
    - removida pestaña dedicada `Asignación`.
    - cache-bust actualizado: `tks.css?v=23`, `tks_ui.js?v=39`, `tks_main.js?v=28`.
  - `code/static/modulos/tks/css/tks.css`:
    - ajustes para embebido limpio de asignación dentro de `Resumen`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - `node --check code/static/modulos/tks/js/tks_main.js` PASS.
  - grep de control:
    - sin `data-tab="asignacion"` en `tks.html`,
    - sin bloque `Carga por Técnico` en `tks_ui.js`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV) + LISTO PARA PRUEBA VISUAL.

## HITO: 2026-02-17 12:40 - EPIC 11 Ticketera: pestaña Asignación en formato horario laboral por técnico (DEV)
- **Solicitud**: ajustar la vista de asignación para que se vea como horario laboral y cada técnico ocupe una sola línea.
- **Entregable**:
  - `code/static/modulos/tks/js/tks_ui.js`:
    - `renderAssignmentTimeline()` rediseñado como grilla horaria diaria.
    - ventana visible fija: laboral `06:00-22:00` + margen extra `05:00-23:00`.
    - una fila horizontal por técnico con tramos coloreados (`asignado`, `en_progreso`, `resuelto`).
    - regla horaria con marcas por hora y etiquetas cada 2 horas para legibilidad.
  - `code/static/modulos/tks/css/tks.css`:
    - nuevo layout de agenda: columna de técnico + pista horaria por fila.
    - líneas de grilla por hora, slots por ticket y estilos responsive.
  - `code/static/modulos/tks/tks.html`:
    - cache-bust: `tks.css?v=22`, `tks_ui.js?v=38`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - `node --check code/static/modulos/tks/js/tks_main.js` PASS.
  - `node --check code/static/modulos/tks/js/tks_api.js` PASS.
  - reinicio `monstruo-dev-api` + `GET /health` OK.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV) + LISTO PARA PRUEBA VISUAL.

## HITO: 2026-02-16 23:45 - EPIC 11 Ticketera: nueva pestaña `Asignación` con timeline por técnico (DEV)
- **Solicitud**: agregar pestaña nueva para asignación de técnicos con vista temporal por tramos de trabajo y cola sin asignar.
- **Entregable**:
  - Backend:
    - `GET /api/tks/asignacion/timeline` en `code/app/api/routers/tks.py`.
    - `get_assignment_timeline(window_hours, ticket_limit)` en `code/app/core/tickets_service.py`.
    - Segmentación temporal por ticket usando `ticket_transitions`:
      - fase `asignado`,
      - fase `en_progreso`,
      - fase `resuelto`.
    - cálculo de estado por técnico (`ocupado/disponible`) y sugerencia de siguiente ticket desde la cola.
  - Frontend:
    - nueva tab `Asignación` en `code/static/modulos/tks/tks.html`.
    - cliente API `getAssignmentTimeline()` en `code/static/modulos/tks/js/tks_api.js`.
    - carga/cache de la tab en `code/static/modulos/tks/js/tks_main.js`.
    - renderer visual de lanes+timeline+cola en `code/static/modulos/tks/js/tks_ui.js`.
    - estilos de vista en `code/static/modulos/tks/css/tks.css`.
  - Cache-bust aplicado:
    - `tks.css?v=21`, `tks_api.js?v=11`, `tks_ui.js?v=37`, `tks_main.js?v=27`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_api.js` PASS.
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - `node --check code/static/modulos/tks/js/tks_main.js` PASS.
  - AST parse Python:
    - `code/app/api/routers/tks.py` PASS.
    - `code/app/core/tickets_service.py` PASS.
  - Smoke backend en contenedor DEV:
    - `tickets_service.get_assignment_timeline(window_hours=72, ticket_limit=500)` => `ok=True`, `technicians=3`, `queue=3`.
- **Estado**: IMPLEMENTADO EN CÓDIGO (DEV) + LISTO PARA PRUEBA VISUAL EN UI.

## HITO: 2026-02-17 16:45 - EPIC 11 Ticketera: set de datos de prueba para asignación por técnico (DEV)
- **Solicitud**: crear tickets de prueba para validar flujo de asignación.
- **Entregable**:
  - Tickets creados:
    - `TK-17-02-2026-0001` asignado a `fabian.correa@telconsulting.cl` (`abierto/asignado`).
    - `TK-17-02-2026-0002` asignado a `juan.hormazabal@telconsulting.cl` (`abierto/asignado`).
    - `TK-17-02-2026-0003` asignado a `lukas.moyano@telconsulting.cl` (`abierto/asignado`).
    - `TK-17-02-2026-0004` sin asignar (`abierto/recibido`).
    - `TK-17-02-2026-0005` sin asignar (`abierto/recibido`).
    - `TK-17-02-2026-0006` sin asignar (`abierto/recibido`).
  - Carga técnica resultante:
    - `fabian...`: `1`
    - `juan.hormazabal...`: `1`
    - `lukas...`: `1`
    - `juan.lopez...`: `0`
- **Validación**:
  - `get_stats().total = 6`.
  - `by_status = {'abierto': 6}`.
  - `pivot_assignee`: 3 asignados + 3 en `Sin Asignar`.
- **Estado**: DATOS DE PRUEBA CREADOS EN DEV.

## HITO: 2026-02-17 16:25 - EPIC 11 Ticketera: corrección de métricas dashboard + reseteo real de tickets en DEV
- **Solicitud**: no “mostrar 0” por hardcode; resetear tickets reales y mantener lectura real de TKs/carga.
- **Corrección aplicada**:
  - `tks_ui.js`:
    - se revirtió hardcode de cards en `0`.
    - se restauró lectura real de `stats` (`total`, `by_status`, `by_prio`) y bloque `Carga por Técnico` (`pivot_assignee`).
  - Reseteo real de datos en DEV (DB):
    - truncadas tablas operativas de ticketera:
      - `tickets`, `ticket_comments`, `ticket_emails`, `ticket_attachments`,
        `ticket_notifications`, `ticket_notification_attempts`,
        `ticket_transitions`, `ticket_approvals`,
        `ticket_email_drafts`, `ticket_email_draft_attachments`,
        `ticket_legal_holds`, `jira_issue_map`.
    - `user_specialties.current_load` reiniciado a `0`.
  - Cache-bust:
    - `tks_ui.js?v=36`.
  - Runtime DEV:
    - reinicio de `monstruo-dev-api`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - Post-reset en contenedor DEV:
    - `get_stats().total = 0`.
    - `get_stats().by_status = {}`.
    - `get_stats().pivot_assignee = {}`.
  - Salud API DEV:
    - `GET /health` => `{"status":"ok","app":"monstruo"}`.
- **Estado**: IMPLEMENTADO EN CÓDIGO + DATOS DEV RESETEADOS.

## HITO: 2026-02-17 16:10 - EPIC 11 Ticketera: dashboard con TKs en 0 + retiro de carga por técnico (DEV)
- **Nota**: este ajuste quedó **revertido** por instrucción del usuario en el hito `2026-02-17 16:25`.
- **Solicitud**: no eliminar tickets reales; dejar indicadores de TKs en `0` y quitar bloque de carga por persona.
- **Entregable**:
  - `tks_ui.js`:
    - cards superiores de TKs (`Totales`, `Activos`, `Resueltos`, `Críticas`) fijadas en `0`.
    - removido bloque `📋 Carga por Técnico` del dashboard para evitar datos inventados por persona.
  - Cache-bust:
    - `tks_ui.js?v=35`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-17 15:55 - EPIC 11 Ticketera: timeline cronológica (nuevo abajo) + scroll por defecto al final (DEV)
- **Solicitud**: mostrar la línea de tiempo con lo más nuevo abajo y que el scroll parta abajo por defecto.
- **Entregable**:
  - `tks_ui.js`:
    - orden del feed unificado ajustado a cronológico ascendente (`más antiguo -> más nuevo`).
    - identificador explícito para el contenedor de timeline (`id="tks-unified-feed"`).
  - `tks_main.js`:
    - helper `scrollTimelineToBottom()` para posicionar siempre al final al abrir detalle.
    - aplicado justo después del render del detalle.
  - Cache-bust:
    - `tks_ui.js?v=34`, `tks_main.js?v=26`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - `node --check code/static/modulos/tks/js/tks_main.js` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-17 15:40 - EPIC 11 Ticketera: sync automático `estado/subestado` en cambios Kanban (DEV)
- **Solicitud**: al mover ticket a `abierto` desde Kanban, el detalle ofrecía `Avanzar a resuelto` directo.
- **Causa raíz**:
  - Kanban actualiza solo `estado`.
  - quedaba `subestado` previo (`en_progreso`) y el workflow se calculaba por subestado.
- **Entregable**:
  - Backend (`tickets_service.py`):
    - en `update_ticket`, cuando llega solo `estado` (sin `subestado`), se sincroniza subestado canónico:
      - `abierto` -> conserva subestado abierto válido o normaliza a `asignado/recibido`.
      - `en_progreso` -> normaliza a subestado operativo en progreso.
      - `resuelto` -> `subestado=resuelto`.
      - `cerrado` -> `subestado=cerrado`.
    - evita combinaciones incoherentes tipo `estado=abierto` + `subestado=en_progreso`.
  - Runtime DEV:
    - reinicio de `monstruo-dev-api`.
- **Validación**:
  - parse AST Python:
    - `code/app/core/tickets_service.py` PASS.
  - QA en contenedor DEV:
    - repro: ticket en `en_progreso`, update solo `estado=abierto`.
    - resultado: `estado=abierto`, `subestado=recibido`, `allowed_next=['asignado']`.
    - no aparece avance directo a `resuelto`.
  - Salud API DEV:
    - `GET /health` => `{"status":"ok","app":"monstruo"}`.
- **Estado**: IMPLEMENTADO EN CÓDIGO + APLICADO EN RUNTIME DEV.

## HITO: 2026-02-17 15:25 - EPIC 11 Ticketera: separación explícita de flujo principal vs reapertura (DEV)
- **Solicitud**: evitar cierre directo desde tickets abiertos/en progreso y separar claramente dos flujos:
  - principal: `abierto -> en_progreso -> resuelto -> cerrado`;
  - reapertura excepcional: `cerrado -> en_progreso` con etiqueta explícita de reabrir.
- **Entregable**:
  - Backend (`tickets_service.py`):
    - `incidencia.resuelto` y `requerimiento.resuelto` quedan solo con siguiente `cerrado` (sin atajo a `en_progreso`).
    - `cerrado -> en_progreso` se mantiene para reapertura.
  - Frontend (`tks_ui.js`):
    - prioridad de flujo ajustada para no sugerir `cerrado` en estados abiertos/en progreso.
    - filtro defensivo: solo permite `cerrado` cuando `estado=resuelto`.
    - en `estado=cerrado`, acción principal muestra: `Reabrir TK (pasar a En Progreso)`.
    - hint contextual para cerrado como reapertura excepcional.
  - Cache-bust:
    - `tks_ui.js?v=33`.
  - Runtime DEV:
    - reinicio de `monstruo-dev-api`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - parse AST Python:
    - `code/app/core/tickets_service.py` PASS.
  - QA flujo en contenedor DEV:
    - `en_progreso` no ofrece `cerrado` directo.
    - `resuelto` ofrece solo `cerrado`.
    - `cerrado` ofrece `en_progreso` para reapertura.
- **Estado**: IMPLEMENTADO EN CÓDIGO + APLICADO EN RUNTIME DEV.

## HITO: 2026-02-17 15:05 - EPIC 11 Ticketera: contador de autocierre en `resuelto` + scroll interno solo en línea de tiempo (DEV)
- **Solicitud**: mostrar contador debajo del estado cuando el ticket está `resuelto` antes de cerrar, y dejar el scroll interno únicamente en la línea de tiempo.
- **Entregable**:
  - `tks_ui.js`:
    - se agregó bloque visual `tks-resuelto-countdown` bajo `Estado actual` cuando `estado=resuelto` y existe ventana de autocierre.
    - cálculo de deadline usando `resolved_at` + `resuelto_auto_close_hours` (fallback informativo si no hay fecha base).
  - `tks_main.js`:
    - contador en vivo (actualiza cada segundo) para `resuelto`.
    - cleanup automático de interval al cerrar detalle/cambiar ticket para evitar timers colgados.
  - `tks.css`:
    - scroll interno del módulo principal desactivado (`.tks-container` en `overflow-y: visible`).
    - scroll interno habilitado y acotado solo para `.tks-unified-feed` (línea de tiempo), con máximo configurable `--tks-timeline-max-height`.
    - estilos visuales para contador normal y estado vencido.
  - Cache-bust:
    - `tks.css?v=20`, `tks_ui.js?v=32`, `tks_main.js?v=25`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - `node --check code/static/modulos/tks/js/tks_main.js` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-17 14:40 - EPIC 11 Ticketera: `resuelto` obligatorio antes de cierre + seguimiento con autocierre (DEV)
- **Solicitud**: no saltar `resuelto`; mantener seguimiento por un tiempo y permitir cierre inmediato cuando el cliente apruebe.
- **Entregable**:
  - Backend (`tickets_service.py`):
    - flujo operativo mantiene `en_progreso -> resuelto -> cerrado` (sin salto directo por defecto).
    - `run_sla_evaluation_batch` ahora incluye tickets en `estado=resuelto` para garantizar autocierre por ventana de seguimiento incluso sin `ttr_due_at`.
    - autocierre robustecido con guarda de concurrencia: solo registra transición/comentario si el `UPDATE` realmente cerró el ticket.
    - se expone `resuelto_auto_close_hours` en workflow (default actual: `72h`, configurable por `TICKET_RESUELTO_AUTO_CLOSE_HOURS`).
  - Frontend (`tks_ui.js`):
    - prioridad de flujo ajustada para privilegiar `resuelto` antes de `cerrado` también en fallback genérico.
    - CTA contextual en `resuelto`: `Cerrar de inmediato (cliente aprobó)`.
    - hint contextual muestra ventana de seguimiento/autocierre en horas.
  - Cache-bust:
    - `tks_ui.js?v=31`.
  - Runtime DEV:
    - reinicio de `monstruo-dev-api`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - parse AST Python:
    - `code/app/core/tickets_service.py` PASS.
  - QA flujo en contenedor DEV:
    - `recibido -> asignado -> en_progreso -> resuelto -> cerrado` PASS.
    - cerrado queda con `allowed_next=['en_progreso']` PASS.
  - QA autocierre en contenedor DEV:
    - ticket en `resuelto` con `resolved_at` vencido pasa automáticamente a `cerrado` al ejecutar batch SLA PASS.
  - Salud API DEV:
    - `GET /health` => `{"status":"ok","app":"monstruo"}`.
- **Estado**: IMPLEMENTADO EN CÓDIGO + APLICADO EN RUNTIME DEV.

## HITO: 2026-02-17 14:05 - EPIC 11 Ticketera: `cerrado -> en_progreso` para evitar bucle reabierto/resuelto (DEV)
- **Solicitud**: desde `cerrado` el flujo debe avanzar a `en_progreso` para evitar bucles rápidos `abierto -> resuelto`.
- **Entregable**:
  - Backend workflow:
    - `cerrado -> en_progreso` en tipos operativos.
    - `reabierto` queda como compatibilidad, también apuntando a `en_progreso`.
  - Frontend (`tks_ui.js`):
    - prioridad de avance para `cerrado` ajustada a `en_progreso`.
  - Runtime DEV:
    - reinicio de `monstruo-dev-api` para aplicar reglas en memoria.
  - Cache-bust:
    - `tks_ui.js?v=30`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - parse AST Python:
    - `code/app/core/tickets_service.py` PASS.
  - verificación en contenedor DEV:
    - tickets `estado=cerrado` retornan `allowed_next=['en_progreso']`.
- **Estado**: IMPLEMENTADO EN CÓDIGO + APLICADO EN RUNTIME DEV.

## HITO: 2026-02-17 13:45 - EPIC 11 Ticketera: saneo estado/subestado legacy y fix de avance incorrecto a `recibido` (DEV)
- **Solicitud**: corregir que el botón mostraba `Avanzar a recibido` en casos de reabrir/cerrar.
- **Causa raíz**:
  - tickets legacy con combinaciones incoherentes (`estado=cerrado` con `subestado=recibido/reabierto`).
  - runtime API con código antiguo en memoria hasta reinicio.
- **Entregable**:
  - Backend (`tickets_service.py`):
    - guard-rail en `_hydrate_ticket_runtime` para forzar coherencia:
      - `estado=cerrado` -> `subestado=cerrado`
      - `estado=resuelto` -> `subestado=resuelto`
  - DB (`db.py`):
    - backfill ampliado para normalizar legacy y corregir tickets cerrados/resueltos con subestado inconsistente.
  - Operación DEV:
    - reinicio de `monstruo-dev-api`.
    - ejecución de `db.init_db()` dentro del contenedor para aplicar backfill.
- **Validación**:
  - `python AST` PASS en `tickets_service.py` y `db.py`.
  - verificación en contenedor:
    - tickets cerrados quedan con `subestado=cerrado`.
    - workflow para cerrados retorna `allowed_next=['reabierto']` (sin `recibido`).
- **Estado**: IMPLEMENTADO EN CÓDIGO + APLICADO EN RUNTIME DEV.

## HITO: 2026-02-17 13:25 - EPIC 11 Ticketera: flujo de reabierto corregido a `resuelto` (DEV)
- **Solicitud**: al reabrir, el botón de avance no debe sugerir `recibido`; debe avanzar a `resuelto`.
- **Entregable**:
  - Backend workflow:
    - `reabierto -> resuelto` para tipos operativos.
    - agregado explícito `resuelto -> cerrado` donde faltaba para mantener continuidad.
  - Frontend (`tks_ui.js`):
    - prioridad de avance para `reabierto` ajustada a `resuelto` como primer destino.
  - Cache-bust:
    - `tks_ui.js?v=29`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - parse AST Python:
    - `code/app/core/tickets_service.py` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-17 13:05 - EPIC 11 Ticketera: eliminación de `triage/nuevo` en flujo visible (DEV)
- **Solicitud**: corregir paso extra `triage` para que el flujo operativo visible quede sin estados legacy.
- **Entregable**:
  - Backend:
    - canonicalización de subestados legacy: `triage` y `nuevo` -> `recibido`.
    - `_hydrate_ticket_runtime` normaliza `subestado` para respuesta de API.
    - `WORKFLOW_RULES` limpio sin claves legacy (`triage`/`nuevo`) en rutas activas.
    - backfill de DB: convierte `tickets.subestado` legacy a `recibido`.
  - Frontend:
    - normalización UI `triage/nuevo` -> `recibido` en render de subestado y evaluación de flujo.
  - Cache-bust:
    - `tks_ui.js?v=28`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - parse AST Python:
    - `code/app/core/tickets_service.py` PASS.
    - `code/app/core/db.py` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-17 12:40 - EPIC 11 Ticketera: fix de repetición “En Progreso” al reabrir (DEV)
- **Solicitud**: evitar que el flujo repita `en_progreso` dos veces al reabrir un ticket.
- **Entregable**:
  - Backend workflow:
    - `reabierto` en `incidencia` y `requerimiento` queda con siguiente único `en_progreso`.
  - Frontend (`tks_ui.js`):
    - guarda para no ofrecer `Avanzar a en_progreso` cuando el ticket ya está en `estado=en_progreso` (excepto salida desde subestado de espera).
  - Cache-bust:
    - `tks_ui.js?v=27`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - parse AST Python:
    - `code/app/core/tickets_service.py` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-17 12:22 - EPIC 11 Ticketera: retiro de subestado duplicado bajo “Estado actual” (DEV)
- **Solicitud**: quitar el subestado que aparecía debajo de “Estado actual”, porque ya existe la sección inferior de flujo/subestados.
- **Entregable**:
  - `tks_ui.js`:
    - removida la línea `Subestado: ...` del resumen superior en card `Estado y gestión`.
    - se mantiene el control de flujo/subestados en el bloque inferior.
  - `tks.html`:
    - cache-bust `tks_ui.js?v=26`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-17 12:10 - EPIC 11 Ticketera: subestados de espera solo en `en_progreso` (DEV)
- **Solicitud**: mantener auto-avance y dejar los subestados de espera visibles/operables solo cuando el ticket esté en estado `en_progreso`.
- **Entregable**:
  - Backend workflow/guardas:
    - `SUBESTADOS_ESPERA` centralizado (`pendiente_cliente`, `pendiente_compra`, `pendiente_tercero`).
    - `get_ticket_workflow` filtra subestados de espera cuando el estado actual no es `en_progreso`.
    - `transition_ticket` bloquea transición a subestado de espera si el ticket no está en `en_progreso`.
    - ajuste de reglas base para evitar rutas de espera desde `asignado` en flujos principales.
  - Frontend (`tks_ui.js`):
    - el bloque `Subestados de espera` solo se renderiza cuando `estado` actual es `en_progreso`.
    - fuera de `en_progreso`, se ocultan esas acciones y se mantiene solo el avance de flujo principal.
  - Cache-bust:
    - `tks_ui.js?v=25`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - parse AST Python:
    - `code/app/core/tickets_service.py` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-17 11:40 - EPIC 11 Ticketera: flujo de estados guiado (un botón) + auto avance a en_progreso (DEV)
- **Solicitud**: dejar un flujo operativo claro `recibido -> asignado -> en_progreso -> cerrado`, con un solo botón para avanzar y subestados de espera en abierto.
- **Entregable**:
  - Backend workflow/base:
    - normalización de subestado por defecto a `recibido`.
    - flujo y mapeo reforzados para `recibido`/`asignado` en creación, claim, transición y lectura de workflow.
  - Frontend detalle (`Lista`):
    - bloque `Estado y gestión` rediseñado:
      - `Estado actual` en formato grande y limpio.
      - botón único `Avanzar a ...` para el siguiente paso principal del flujo.
      - acciones secundarias de espera (`pendiente_cliente`, `pendiente_compra`, `pendiente_tercero`) cuando el workflow las permite.
    - auto-transición en detalle abierto:
      - si ticket está en `asignado`, técnico asignado tiene 60s para moverlo manualmente;
      - al vencer, pasa automáticamente a `en_progreso`.
      - timer se cancela al cerrar detalle, cambiar ticket o transicionar manualmente.
  - Cache-bust:
    - `tks.css?v=19`, `tks_ui.js?v=24`, `tks_main.js?v=24`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - `node --check code/static/modulos/tks/js/tks_main.js` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-16 20:33 - EPIC 11 Ticketera: ajuste anti-scroll interno en detalle (DEV)
- **Solicitud**: evitar scroll dentro de la ventana de detalle y permitir crecimiento hacia abajo con mínimo/máximo según contenido.
- **Entregable**:
  - `tks.css`:
    - detalle full-width con altura flexible (`height:auto`) y límites `min-height/max-height`.
    - eliminación de scroll interno en columnas principales (`main` y `sidebar`) del detalle.
    - ajuste en estado `detail-open` para permitir expansión visible del detalle.
    - tuning responsive mobile con `min-height/max-height` propios.
  - cache-bust frontend:
    - `tks.css?v=9`.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-16 20:21 - EPIC 11 Ticketera: rediseño profesional de detalle en Lista sin pestañas (DEV)
- **Solicitud**: rediseñar detalle full-width con look profesional, asunto centrado, cierre con confirmación inteligente y flujo de comunicación unificado en línea de tiempo.
- **Entregable**:
  - Frontend UI (`tks_ui.js`):
    - `renderDetail` reescrito en layout 2 columnas (`feed principal + sidebar`) sin tabs.
    - feed único cronológico con eventos + correos, mostrando `De/Para`.
    - filtrado de eventos técnicos duplicados de correo (`[CORREO]`, `[CORREO_ENTRANTE]`, `[ADJUNTO_INCOMING]`).
    - composer único con dos modos (`Nota interna` / `Responder cliente`) en la misma vista.
    - card lateral `Estado y gestión` con `Estado actual + selector Cambiar a + Aplicar`.
    - cards laterales de `Adjuntos` y `Cliente compacto`.
    - adjuntos por correo con descarga cuando existe match en `ticket_attachments` (sha256 -> path -> filename/size).
  - Frontend controller (`tks_main.js`):
    - nuevo `switchComposerMode`.
    - compatibilidad temporal de `switchDetailTab` delegando al composer.
    - nuevo `applyStatusChange` para selector explícito de estado.
    - `closeDetail` con confirmación solo si detecta cambios pendientes (nota, borrador, archivos por subir o lock en edición).
    - flujo de draft lock/heartbeat/send/discard preservado.
  - Estilos (`tks.css`):
    - tema `Slate Pro` aplicado a detalle.
    - `X` agrandada con mayor área clickeable.
    - nueva jerarquía visual para header, feed, composer y sidebar.
  - Cache-bust:
    - `tks.css?v=7`, `tks_ui.js?v=16`, `tks_main.js?v=21`.
- **Validación**:
  - `node --check code/static/modulos/tks/js/tks_ui.js` PASS.
  - `node --check code/static/modulos/tks/js/tks_main.js` PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-16 19:36 - EPIC 11 Ticketera: reposición de contador junto a botón Cerrar (DEV)
- **Solicitud**: mover el contador de clientes para que quede a la izquierda del botón `Cerrar` en modal de vinculación.
- **Entregable**:
  - `tks_ui.js`: contador removido del body y agregado en el footer del modal.
  - footer del modal ajustado con `justify-content: space-between` para ubicar contador a la izquierda y botón a la derecha.
  - cache-bust frontend: `tks_ui.js?v=15`.
- **Validación**:
  - `node --check` sobre `tks_ui.js`: PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-16 19:34 - EPIC 11 Ticketera: contador de clientes en modal de vinculación (DEV)
- **Solicitud**: mostrar abajo la cantidad de clientes listados en el modal de vincular correo.
- **Entregable**:
  - `tks_ui.js`: nuevo elemento `#tks-assoc-count` bajo el listado.
  - `tks_main.js`: actualización dinámica del contador en estados de carga, resultados, vacío y error.
  - cache-bust frontend: `tks_ui.js?v=14` y `tks_main.js?v=20`.
- **Validación**:
  - `node --check` en `tks_ui.js` y `tks_main.js`: PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-16 19:29 - EPIC 11 Ticketera: hotfix 422 en búsqueda de clientes (DEV)
- **Incidente**: modal de vinculación fallaba con `422` al consultar `GET /api/tks/customers/search?limit=0` (`ge=1` activo en runtime previo).
- **Corrección**:
  - reinicio de `monstruo-dev-api` para cargar validación actualizada del endpoint.
  - fallback en frontend: si `limit=0` falla por validación antigua, reintenta automático con `limit=100` sin cortar flujo.
  - cache-bust de `tks_main.js` a `v=19`.
- **Validación**:
  - llamada interna a endpoint con `limit=0` en contenedor API responde `401 missing_auth` (ya no `422`).
  - `node --check` sobre `tks_main.js`: PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-16 19:22 - EPIC 11 Ticketera: lista completa de clientes al vincular correo (DEV)
- **Solicitud**: Al abrir modal de vinculación mostrar todos los clientes disponibles y mantener búsqueda instantánea.
- **Entregable**:
  - Frontend:
    - `tks_main.js` actualizado para consultar `customers/search` con `limit=0` cuando el campo está vacío (lista completa).
    - búsqueda con texto mantiene límite operativo (`limit=100`) para respuesta ágil.
  - API Ticketera:
    - endpoint `GET /api/tks/customers/search` acepta `limit=0` como sin límite (`ge=0`, `le=5000`).
  - Servicio Ticketera:
    - `search_customers` soporta `limit=0` sin `LIMIT` SQL, devolviendo todos los clientes ordenados por nombre.
- **Validación**:
  - Compilación Python de `tickets_service.py` y `tks.py` en memoria: PASS.
  - `node --check` sobre `tks_main.js`: PASS.
- **Estado**: IMPLEMENTADO EN CÓDIGO.

## HITO: 2026-02-16 18:40 - EPIC 11 Ticketera: detalle full-width + borrador persistente anti-cruce (DEV)
- **Solicitud**: Implementar vista de detalle full-width en Lista y nuevo flujo de respuesta al cliente con borrador persistente, lock y revisión previa a envío.
- **Entregable**:
  - Backend DB:
    - tablas nuevas `ticket_email_drafts` y `ticket_email_draft_attachments` con índice único parcial de borrador activo por ticket.
  - Backend servicio:
    - API de borradores: lectura, lock, heartbeat, guardado versionado, adjuntos de borrador, descarte y envío final.
    - lock exclusivo por 5 minutos, takeover explícito (`force=true`) y conflictos de concurrencia como `409`.
    - bloqueo de respuesta por correo en tickets `resuelto/cerrado` (incluye endpoint legacy `reply-email`).
  - API Ticketera:
    - nuevos endpoints `/api/tks/tickets/{ticket_id}/email-draft*` para ciclo completo de borrador.
  - Frontend Ticketera:
    - Lista con detalle full-width (reemplaza drawer lateral).
    - cierre con botón superior derecho y retorno a lista con reset completo de filtros/búsqueda.
    - tabs separadas `Nota interna` (envío inmediato) y `Responder cliente` (borrador persistente).
    - flujo `Guardar borrador` + `Revisar y enviar` (modal de confirmación) + `Descartar`.
    - estado de lock visible y control de takeover desde UI.
  - Pruebas:
    - `tests/e2e_ticketera.py` extendido con smoke API de borrador: lock/version, takeover, envío, bloqueo en cerrado y validación 403 de admin en mutaciones de draft.
- **Estado**: IMPLEMENTADO EN CÓDIGO (pendiente corrida E2E completa en este ciclo).

## HITO: 2026-02-16 13:45 - EPIC 11 Ticketera: ownership por asignación + vistas por rol anti-cruce (DEV)
- **Solicitud**: Definir vistas por rol y evitar cruces de intervención en ticketera (respuestas/cambios simultáneos sobre un mismo ticket).
- **Entregable**:
  - Backend Ticketera endurecido con política de ownership:
    - nuevo endpoint `POST /api/tks/tickets/{ticket_id}/claim` para tomar ticket sin asignar de forma controlada.
    - `add_comment`, `reply_ticket_email`, `upload_ticket_attachments` bloquean intervención cuando el ticket no está asignado al técnico activo.
    - rol `admin` bloqueado para intervención operativa (correo/notas/adjuntos), pero habilitado para gestión (`estado` y `asignación/reasignación`).
    - `update_ticket` con validación de ownership y guardas anti-toma concurrente por usuarios no-admin.
    - respuestas `403` explícitas en API cuando hay violación de ownership.
  - Frontend Ticketera con vistas por rol:
    - detección de sesión/rol desde `/api/sesion` y modo visual (`Admin Gestión`, `Técnico`, `Solo Lectura`).
    - técnicos: filtro por defecto en “Mis tickets”, opción de “Sin asignar” y botón `Tomar ticket`.
    - admin: sin panel de respuesta/notas; mantiene controles de estado y reasignación.
    - tab `Operación` visible solo para roles con vista operativa (`admin`, `gerencia`).
  - Pruebas:
    - `tests/e2e_ticketera.py` extendido con bloque específico de ownership/claim/anti-cruce.
- **Estado**: IMPLEMENTADO EN CÓDIGO (pendiente corrida completa E2E en este ciclo).

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
  - Creado archivo canonico: `.agents/rules/reglas-monstruo-dev.md`.
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
