# Ticketera - Bitácora de depuración de módulos visibles

Fecha: 2026-04-05
Contexto: depuración de por qué Dashboard/Configuración muestran módulos, pero Ticketera no los muestra correctamente para ciertos usuarios en dev.

---

## Objetivo

Entender por qué la Ticketera (`9005`) no mostraba módulos en el sidebar, incluso cuando otras apps como Dashboard (`9001`) y Configuración sí los mostraban.

---

## Hallazgos confirmados

### 1. La arquitectura actual es híbrida: módulos independientes + shell compartido
Se confirmó en `/srv/monstruo_dev` que existen apps separadas por módulo:
- gateway
- ticketera
- erp
- bodega
- crm
- pmo
- fundacion
- ia

Cada una tiene backend y UI propia, pero comparten shell/UI común mediante:
- `gateway/shared/ui/js/sidebar.js`
- `gateway/shared/ui/js/utilidades.js`
- `gateway/shared/ui/css/monstruo.css`

Esto implica que un bug puede venir de:
- backend del módulo
- shell compartido
- configuración efectiva del usuario
- o una combinación de las tres

---

### 2. El legacy sigue existiendo, pero no fue la causa inmediata del bug actual
Se encontró un árbol legacy vivo en:
- `/srv/monstruo_dev/plataforma/legacy/code/static/...`

Ese legacy todavía mantiene su propio `_compartido/js/sidebar.js` con lógica antigua, pero para este incidente puntual no fue la causa inmediata del fallo visible en Ticketera.

---

### 3. Había desalineación de versiones del shell nuevo entre módulos
Antes del saneamiento, los HTML nuevos referenciaban distintas versiones cacheadas:
- Ticketera: `sidebar.js?v=87`, `utilidades.js?v=208`
- otros módulos: `sidebar.js?v=82/84`, `utilidades.js?v=209`

Se unificó en dev a:
- `sidebar.js?v=88`
- `utilidades.js?v=210`

Archivos tocados:
- `ticketera/ui/tks.html`
- `bodega/ui/bodega.html`
- `crm/ui/crm.html`
- `erp/ui/erp.html`
- `pmo/ui/pmo.html`
- `fundacion/ui/fundacion.html`
- `ia/ui/ia.html`
- `gateway/dashboard/dashboard.html`
- `gateway/dashboard/inicio.html`
- `gateway/configuracion/configuracion.html`

Además se eliminó debug explícito del shared sidebar (`window.__sidebar_debug`, `console.log('[sidebar-debug]', ...)`) para dejar el shell más limpio.

Backup del shared sidebar dejado en:
- `/srv/monstruo_dev/gateway/shared/ui/js/sidebar.js.bak_ticketera_audit`

---

### 4. Ticketera standalone sí tenía una inconsistencia real en `/api/sesion`
Se detectó que `ticketera/main.py` todavía usaba una lógica vieja:
- leía `allowed_modules` directamente desde DB
- si estaba vacío, devolvía `[]`

Se alineó con la lógica del gateway para que:
- si hay override explícito de `allowed_modules`, se respete
- si no hay override válido, derive módulos por rol/permisos

Archivo parchado:
- `/srv/monstruo_dev/ticketera/main.py`

Backup dejado en:
- `/srv/monstruo_dev/ticketera/main.py.bak_ticketera_session_align`

Luego se reinició el contenedor:
- `monstruo-dev-ticketera`

---

### 5. Los IDs de módulo entre backend y sidebar sí coinciden
Se revisó `UI_MODULES` y `PERMISSION_TO_MODULE_MAP` tanto en gateway como en ticketera.

IDs confirmados:
- `dashboard`
- `tks`
- `pmo`
- `erp`
- `crm`
- `bodega`
- `ia`
- `zabbix`
- `fundacion`
- `config`

Conclusión:
No había mismatch tipo `ticketera` vs `tks` ni `configuracion` vs `config`.

---

### 6. El usuario y rol sí aparecen en Ticketera
El usuario reportó que en la Ticketera sí se muestra correctamente:
- el nombre del usuario
- el rol

Eso implica que:
- `/api/sesion` responde
- la cookie/sesión no está completamente rota
- el fetch del sidebar no está fallando del todo

Por tanto, el problema se acotó a `allowed_modules` / render de módulos visibles.

---

### 7. La base real sí estaba siendo usada y los datos explicaban parte de la confusión
Se inspeccionó Postgres dentro de `monstruo-dev-postgres` y se confirmaron usuarios reales en `auth.users`.

Estado observado en un momento de la investigación:
- `juan.lopez@telconsulting.cl` → rol `sistemas` → `allowed_modules = []`
- `lukas.moyano@telconsulting.cl` → rol `sistemas` → `allowed_modules = []`
- `diego@telconsulting.cl` → rol `gerencia` → `allowed_modules = ["dashboard", "tks"]`
- `fabian.correa@telconsulting.cl` → rol `encargado_mesa` → `allowed_modules = ["dashboard", "tks"]`
- `sistemas@telconsulting.cl` → rol `admin` → `allowed_modules = ["*"]`

Esto llevó inicialmente a pensar que el problema era mezcla entre override manual y fallback por rol.

Más tarde, el usuario aclaró un punto decisivo:
- en Configuración se pueden elegir manualmente los módulos visibles por usuario
- por tanto, `allowed_modules` sí debe seguir funcionando como override administrativo real

---

### 8. Luego se corrigieron manualmente los módulos de dos usuarios, y la DB sí reflejó esos cambios
Se verificó en Postgres que los cambios manuales ya estaban guardados:

- `sistemas@telconsulting.cl` → `allowed_modules = ["dashboard", "tks", "pmo", "erp", "crm", "bodega", "ia", "zabbix", "fundacion", "config"]`
- `juan.lopez@telconsulting.cl` → `allowed_modules = ["dashboard", "tks"]`

Conclusión crítica:
**la DB ya contenía exactamente lo esperado**, y aun así la Ticketera seguía sin mostrar módulos.

Esto descartó que el problema actual fuera simplemente "el usuario no tenía módulos seleccionados".

---

## Estado actual del diagnóstico

A esta altura quedaron descartados los siguientes sospechosos:

- mismatch de IDs de módulo entre backend y sidebar
- assets del shared sin cargar en `9005`
- Ticketera standalone con lógica antigua de `/api/sesion`
- datos no actualizados en DB para los dos usuarios probados
- fallo total de sesión/cookie (porque usuario y rol sí aparecen)

---

## Hipótesis vigentes

### Hipótesis A. La Ticketera no está reflejando `allowed_modules` aunque el backend y DB ya estén correctos
Posibles causas:
- el JSON real que ve el navegador en `/api/sesion` no coincide con lo que esperamos
- hay una diferencia entre lo que devuelve el endpoint y lo que usa realmente el sidebar
- hay una ruta/capa de render que termina ignorando los módulos

### Hipótesis B. El problema está del lado frontend/render de sidebar en Ticketera, no en permisos
Como el usuario/rol sí aparecen y la DB ya está bien, podría haber un bug de render específico del sidebar dentro de la app de Ticketera.

### Hipótesis C. Algún estado cacheado del navegador o comportamiento de cliente sigue mostrando una versión vieja
Se pidió probar hard refresh / incógnito, pero el usuario reportó que seguía igual.
Por eso esta hipótesis ya no es la principal, aunque no se puede descartar al 100% sin inspección del navegador.

---

## Qué NO hacer a futuro

- No seguir especulando a ciegas sin ver el JSON real de `/api/sesion` desde el navegador de Ticketera.
- No asumir que porque Dashboard/Config funcionan, Ticketera está viendo exactamente el mismo dato efectivo.
- No tocar más permisos o DB sin primero observar la respuesta real que recibe el sidebar en el navegador.

---

## Siguiente paso real recomendado

### Paso 1. Ver el JSON real desde la consola del navegador en Ticketera
Ejecutar en la consola del navegador de la Ticketera:

```js
fetch('/api/sesion', { credentials: 'include' }).then(r => r.json()).then(console.log)
```

Y revisar específicamente:
- `ok`
- `user`
- `role`
- `roles`
- `allowed_modules`

Esto decidirá el siguiente camino:

#### Si `allowed_modules` sale correcto
Entonces el problema está 100% en render/frontend/sidebar.

#### Si `allowed_modules` sale vacío o incorrecto
Entonces el problema está en la sesión efectiva del navegador o en cómo Ticketera resuelve el endpoint real en runtime.

---

## Pendiente funcional nuevo: adjuntos de correo en el layout central de 3 cuadros

Se agregó como pendiente funcional independiente del bug de módulos:

### Necesidad reportada por el usuario
Cuando un correo tiene muchas imágenes/adjuntos, el bloque central de adjuntos no debe crecer infinito hacia abajo.

Comportamiento deseado:
- el contenedor de adjuntos debe tener alto controlado
- si hay demasiados adjuntos, debe aparecer scroll interno
- no deben mostrarse miniaturas de imagen en ese bloque
- el objetivo es ahorrar espacio en la zona central entre los 3 cuadros del detalle

### Pistas técnicas encontradas
El render actual de adjuntos parece vivir principalmente en:
- `tks_ui.js`
- funciones relacionadas con `renderAttachmentCard(...)`
- clases como:
  - `.tks-email-attachments`
  - `.tks-side-attachments`
  - `.tks-attachment-card`
  - `.tks-attachment-thumb`

Hallazgo clave:
- hoy sí existe render de miniatura para imágenes en `renderAttachmentCard(...)`
- si el adjunto es imagen, genera `<img ...>` dentro de `.tks-attachment-thumb`
- eso probablemente explica por qué el bloque crece demasiado cuando vienen muchos adjuntos visuales

### Hipótesis de implementación futura
Para este pendiente, probablemente haya que:
1. ajustar `renderAttachmentCard(...)` para modo compacto sin miniatura real
2. reemplazar la preview visual por ícono/tipo de archivo
3. aplicar `max-height` + `overflow-y: auto` al contenedor de adjuntos del panel central
4. validar que esto afecte solo el bloque de adjuntos del timeline/correo y no rompa la preview modal individual

### Estado
Pendiente. No implementado aún.

---

## Pendiente funcional nuevo: adjuntar archivos reales en correos de Ticketera

### Necesidad reportada por el usuario
Actualmente quieren poder adjuntar archivos e imágenes reales al responder correos desde Ticketera.

Casos mencionados explícitamente:
- PDF
- imágenes
- otros archivos que se necesiten enviar al cliente

### Problema observado
Hoy el flujo de reply/composer no está resolviendo correctamente el envío de archivos reales como parte del correo saliente, o al menos no de forma confiable/utilizable para el usuario final.

### Pistas técnicas encontradas
Se detectaron zonas relacionadas con adjuntos en el composer dentro de:
- `tks_ui.js`
- `tks_main.dev.js`
- `renderDetail.js`
- `split-detail-composer.js`

Elementos relevantes vistos en el código:
- `#tks-draft-files`
- `#tks-draft-file-list`
- `.tks-draft-attachments`
- funciones de review/borrador que listan adjuntos seleccionados
- mensajes como `Sin adjuntos seleccionados`
- hint de pegar capturas directamente en el reply

### Lectura técnica preliminar
Parece que existe parte del UI para manejar adjuntos en borrador/revisión, pero no está cerrado de extremo a extremo como funcionalidad robusta de envío de archivos reales en correos salientes.

### Qué debería quedar resuelto
1. habilitar `paste` event para pegar capturas directamente en el editor y sumarlas a la lista
2. habilitar drag & drop de archivos en la zona del composer
3. corregir la API backend (`_send_ticket_reply_email`) para que devuelva y guarde los `id` de los adjuntos creados, así no quedan como "históricos muertos" en la UI
4. poder adjuntar imágenes, PDFs y otros archivos desde selector de archivos, arrastrando o pegando
5. que los adjuntos viajen efectivamente en el correo saliente
6. que el usuario vea con claridad qué adjuntos están listos para enviar

### Estado
Completado (Fase 1B).
- Se habilitó paste event y drag&drop en el editor de correos.
- Se reparó el envío en `tickets_service.py` para devolver los IDs y registrarlos correctamente.

---

## Pendiente funcional nuevo: ver adjuntos e imágenes enviados/recibidos desde Ticketera

### Necesidad reportada por el usuario
Además de poder adjuntar archivos, también quieren poder ver correctamente los archivos e imágenes cuando lleguen o cuando se envíen desde Ticketera.

Casos esperados:
- ver imágenes recibidas
- ver PDFs/archivos adjuntos
- poder revisar lo enviado y lo recibido sin perder contexto

### Objetivo funcional
La Ticketera debería permitir visualizar adjuntos de forma clara tanto en:
- correos entrantes
- correos salientes
- historial/feed del ticket
- preview individual cuando corresponda

### Pistas técnicas encontradas
Ya existen piezas relacionadas con preview de adjuntos en:
- `tks_ui.js`
- funciones como `renderAttachmentPreviewModal(...)`
- helpers como `attachmentPreviewKind(...)`, `attachmentCanInlinePreview(...)`
- URLs como `getTicketAttachmentInlineUrl(...)` y `getTicketAttachmentDownloadUrl(...)`

Esto sugiere que ya hay base técnica para preview, pero no necesariamente una experiencia completa/coherente para todos los casos de uso del usuario.

### Qué debería quedar resuelto
1. ver imágenes directamente cuando tenga sentido
2. abrir preview individual de PDFs/archivos compatibles
3. descargar cuando no haya preview inline razonable
4. distinguir mejor adjuntos recibidos vs enviados
5. asegurar que el historial del ticket no pierda acceso a los archivos asociados
6. mantener layout usable aunque haya muchos adjuntos

### Relación con otros pendientes
Este pendiente está conectado con:
- el pendiente de envío real de archivos en correos
- el pendiente de compactar el bloque de adjuntos del layout central

### Estado
Pendiente. No validado aún como experiencia completa de visualización.

---

## Pendiente funcional nuevo: archivar / organizar tickets por cliente

### Necesidad reportada por el usuario
Poder archivar los TKs por cliente.

### Interpretación funcional inicial
Esto puede implicar una o varias de estas capacidades:
- filtrar tickets archivados por cliente
- agrupar historial/tickets cerrados por cliente
- mantener trazabilidad histórica sin mezclar todo en la vista operativa principal
- consultar rápidamente qué pasó con un cliente en periodos anteriores

### Objetivo deseado
Que la Ticketera no solo gestione tickets activos, sino que también permita una organización histórica útil por cliente.

### Posibles líneas de implementación futuras
1. agregar estado o bandera de archivado
2. permitir archivado manual o automático según reglas
3. crear vistas/filtros por cliente + archivado
4. mantener búsqueda y trazabilidad histórica por cliente
5. evitar que el archivado ensucie el flujo operativo diario

### Estado
Pendiente. Requiere definición funcional más fina antes de implementación.

---

## Pendiente funcional nuevo: informe mensual de tickets totales

### Necesidad reportada por el usuario
Poder generar o consultar un informe mensual con el total de tickets.

### Interpretación funcional inicial
El informe mensual podría incluir, al menos:
- total de tickets creados en el mes
- total por cliente
- total por estado
- total por categoría o área
- tendencia comparativa con mes anterior

### Objetivo deseado
Tener una vista ejecutiva/operativa mensual que permita medir volumen y comportamiento de la mesa de ayuda.

### Posibles líneas de implementación futuras
1. definir KPIs mínimos del informe mensual
2. crear consulta agregada por rango mensual
3. permitir filtro por cliente, estado, categoría o responsable
4. habilitar vista en dashboard o módulo de reportes
5. eventualmente permitir exportación

### Estado
Pendiente. No implementado aún.

---

## Hoja de ruta inicial para empezar las mejoras de Ticketera

### Principio rector
Todas las mejoras deben entrar con enfoque profesional:
- cambio pequeño
- alcance acotado
- sin parches rápidos
- sin mezclar muchas capacidades en una sola intervención
- validación entre pasos

---

### Fase 0 — Cerrar el bug de módulos visibles
**Objetivo:** dejar resuelto o al menos totalmente explicado el problema de módulos visibles en Ticketera.

**Por qué va primero:**
No conviene seguir agregando mejoras mientras hay una inconsistencia base en navegación/permisos/render.

**Entrega esperada:**
- identificar si el problema final está en `/api/sesion` real del navegador o en render del sidebar
- documentar causa exacta
- dejar corrección mínima y validada

**No mezclar con:**
- adjuntos
- correo saliente
- reporting
- archivado

---

## Fase 1 — Paquete "Correo y adjuntos" (Completado ✅)
**Estado:** Cerrado. El usuario confirma que puede enviar y recibir archivos correctamente y la visualización es estable.

---

## Fase 2 — Organización histórica y archivado (En curso 🚀)
**Objetivo:** empezar a ordenar la historia operacional sin ensuciar la mesa activa.

**Requerimientos específicos:**
1.  **Auto-archivado de completados:** Los tickets en estado "completado" deben dejar de mostrarse en la vista principal pasadas 12 horas desde su resolución (`resolved_at`).
2.  **Vinculación con Clientes:**
    *   Poder asociar un ticket a un cliente específico (`customer_id`).
    *   Permitir la asignación de cliente a futuro si el ticket no tiene uno inicialmente.
3.  **Consola de Estado/Salud:**
    *   Crear una vista de consola que informe el estado de salud de la aplicación.
    *   Registrar acciones relevantes y dejar constancia de fallos o errores técnicos detectados para auditoría rápida.

**Entrega esperada:**
- Lógica de filtrado temporal para tickets completados.
- UI para asignar/editar cliente en el detalle del ticket.
- Nueva página o componente de "Consola de Aplicación".

---

## Fase 3 — Reporte mensual de tickets (Completado ✅)
**Estado:** Cerrado. Se implementó una nueva pestaña de "Reportes" que genera un informe estadístico del mes en curso.

**Funcionalidades incluidas:**
- **KPIs Principales:** Total de tickets creados, terminados, pendientes y porcentaje de cumplimiento SLA.
- **Top Clientes:** Listado de los clientes con mayor volumen de tickets en el mes.
- **Distribución por Área:** Desglose de tickets por categoría.
- **Resumen Ejecutivo:** Párrafo narrativo con el resumen de gestión del período.

---

## Próximos pasos sugeridos
1.  **Auditoría de UX en Móvil:** Revisar que el nuevo layout de reportes sea legible en dispositivos pequeños.
2.  **Exportación a PDF:** Agregar un botón para descargar el reporte mensual en formato PDF para envío por correo.
3.  **Refactor de Estructura:** Separar los monolitos `tks_main.js` y `tks_ui.js` en componentes más pequeños y mantenibles.

---

### Modo de trabajo obligatorio por cada mejora
Antes de implementar cualquier mejora nueva, preparar siempre:
1. objetivo
2. alcance
3. qué no se toca
4. archivos probables
5. riesgos
6. plan por pasos
7. checklist de validación

---

### Orden recomendado actual
1. cerrar bug de módulos visibles
2. layout compacto de adjuntos
3. adjuntar archivos reales
4. visualizar adjuntos enviados/recibidos
5. archivado/organización por cliente
6. informe mensual de tickets

---

## Depuración Avanzada de Sesión (2026-04-05)

### Problema
A pesar de corregir `COOKIE_DOMAIN` y `COOKIE_SECURE`, el usuario sigue siendo redirigido desde la Ticketera al Dashboard. Esto indica que la cookie de sesión no está siendo validada correctamente por el backend de Ticketera.

### Plan de Diagnóstico Temporal (Aprobado por J3YC1)
Para aislar la causa raíz, se deshabilitará temporalmente la redirección forzosa en la ruta principal (`/`) de la Ticketera.

**Acción:** Comentar el bloque `try...except` en la función `get_index` dentro de `/srv/monstruo_dev/ticketera/main.py`.

**Objetivo:**
- Si la página de la Ticketera carga (aunque sea sin módulos), confirma que el problema es 100% la validación de la cookie (`deps.require_session_hybrid`).
- Si la página sigue sin cargar o muestra otro error, el problema podría ser más profundo (configuración del servidor, etc.).

**Este cambio debe ser revertido inmediatamente después de la prueba.**

---


Se avanzó bastante y se eliminaron varias fuentes reales de ruido:
- se limpió el shell compartido nuevo
- se unificaron versiones de assets
- se alineó Ticketera standalone con Gateway en el contrato de `/api/sesion`
- se confirmó que la DB sí guarda correctamente los módulos seleccionados

Pero el bug visible persiste:

> En Ticketera, el usuario y rol sí se muestran, pero los módulos no aparecen aunque `allowed_modules` ya está correctamente guardado en la base.

Por eso el siguiente paso ya no es más teoría: es inspección directa del JSON real en el navegador de Ticketera.

---

## Incidente operativo - caída de Ticketera dev por error de sintaxis (2026-04-06)

### Resumen
La Ticketera dev en `9005` quedó fuera de servicio no por Docker, red o base de datos, sino por un error de sintaxis en `ticketera/main.py`.

### Causa raíz confirmada
Se había insertado una línea de debug dentro de `check_session_status(...)` en `/api/sesion`, pero quedó mal indentada, rompiendo el bloque `try`:

```python
print(f"DEBUG: [Ticketera] check_session_status - Session validated: {sess}")
```

Error observado en logs:

```python
SyntaxError: expected 'except' or 'finally' block
```

### Efecto operativo
- Uvicorn intentaba recargar por cambios en `ticketera/main.py`
- el proceso no podía importar la aplicación
- el puerto `9005` dejaba de responder correctamente
- desde afuera parecía que la Ticketera estaba "caída"

### Corrección aplicada
Se realizó corrección mínima y segura en dev:
- se eliminó la línea de debug rota
- se validó compilación Python dentro del contenedor con `py_compile`
- se verificó que la app volvió a responder en `9005`
- `/api/sesion` volvió a contestar JSON (`401 missing_auth` sin sesión), lo que confirma que el backend quedó vivo otra vez

Backup dejado en:
- `/srv/monstruo_dev/ticketera/main.py.bak_fix_2026_04_06_0744`

### Lección operativa obligatoria
**Queda prohibido meter `print(...)`, logs sueltos o debugging manual directamente en bloques sensibles (`try/except`, auth, sesión, arranque) sin validación sintáctica inmediata.**

### Regla preventiva nueva
Cada vez que se toque Python backend en dev, especialmente:
- `main.py`
- `deps.py`
- auth
- sesión
- startup
- rutas críticas

hay que hacer siempre esta secuencia mínima antes de dar por bueno el cambio:

1. editar cambio pequeño y aislado
2. correr validación sintáctica (`python -m py_compile ...`)
3. revisar logs del contenedor
4. recién después validar por HTTP

### Qué no hacer de nuevo
- no dejar debug manual en caliente sin compilar
- no asumir que el autoreload detecta errores de forma segura
- no mezclar diagnóstico de sesión con cambios improvisados en `main.py`

### Recomendación profesional siguiente
Agregar una verificación rápida tipo "sanity check" para backend dev antes de reinicios o recargas importantes, idealmente enfocada en:
- compilación Python
- estado del contenedor
- health HTTP básico de `9005`

Esto ayudaría a evitar caídas tontas por errores de edición manual.

---

## Hallazgo confirmado - módulos invisibles en Ticketera dev (2026-04-06)

### Síntoma reportado
- la Ticketera no mostraba módulos en el sidebar
- en algunos casos no aparecía ni siquiera el propio módulo `tks`
- esto ocurría aunque en Configuración el admin tuviera todos los módulos marcados y usuarios normales tuvieran Ticketera marcada

### Verificación de datos reales
Se confirmó desde la DB usada por el contenedor dev que los datos sí estaban guardados:

- `juan.lopez@telconsulting.cl` → `allowed_modules = ["dashboard", "tks"]`
- `sistemas@telconsulting.cl` → `allowed_modules = ["dashboard", "tks", "pmo", "erp", "crm", "bodega", "ia", "zabbix", "fundacion", "config"]`

Esto descartó que el problema fuera simplemente "Configuración no guardó los módulos".

### Causa raíz confirmada
La Ticketera standalone seguía usando una implementación incompleta para `/api/sesion`:

- **Ticketera** usaba `"allowed_modules": _load_allowed_modules(sess["username"])`
- esa función solo leía el JSON directo desde DB
- si no había override válido o venía vacío, devolvía `[]`

En cambio el **Gateway** ya usaba la lógica correcta:
- respeta override explícito si existe
- si no existe o no es válido, deriva módulos por rol/permisos
- contempla admin y permiso `*`

Como el sidebar compartido fue simplificado para confiar **100%** en `allowed_modules` del backend, cualquier `[]` o resolución defectuosa dejaba el menú vacío.

### Corrección aplicada en dev
Se alineó `ticketera/main.py` con la lógica del Gateway:
- se reemplazó la función vieja por `_get_effective_allowed_modules(sess)`
- `/api/sesion` ahora usa esa resolución efectiva y no la lectura mínima previa

Archivo tocado:
- `/srv/monstruo_dev/ticketera/main.py`

Backup dejado:
- `/srv/monstruo_dev/ticketera/main.py.bak_modules_align_2026_04_06_0752`

### Validación técnica realizada
- compilación Python: **OK**
- contenedor recargó correctamente
- logs muestran nuevamente `GET /api/sesion HTTP/1.1 200 OK`

### Interpretación
El problema no estaba en que el usuario "no tuviera módulos" en Configuración, sino en que **Ticketera no aplicaba el mismo contrato efectivo de módulos que el Gateway**.

### Regla preventiva nueva
Queda prohibido mantener lógica duplicada e incompleta entre Gateway y Ticketera para auth/sesión/módulos visibles.

Si un módulo standalone necesita exponer `/api/sesion`, debe usar exactamente el mismo criterio efectivo que Gateway para:
- `allowed_modules`
- fallback por rol/permisos
- caso admin / `*`

### Próximo control recomendado
Validar en navegador real, con sesión iniciada, estos dos casos:
1. admin ve todos los módulos
2. usuario con `dashboard + tks` ve exactamente esos dos

Si después de esta corrección el menú sigue mal en navegador, el siguiente sospechoso ya sería frontend/caché/render y no backend de permisos.

---

## Aclaración crítica de configuración - qué `.env` manda realmente en dev (2026-04-06)

### Resumen corto y sin ambigüedad
**En `monstruo_dev`, los contenedores NO toman su configuración principal desde `ticketera/.env` ni desde `gateway/.env`.**

La configuración real que usan los contenedores levantados por `docker compose` viene desde:

- `/srv/monstruo_dev/plataforma/ops/env/.env.server.dev`

Esto aplica al menos para:
- `monstruo-dev-gateway`
- `monstruo-dev-ticketera`
- y el resto de microservicios definidos en `docker-compose.yaml`

### Fuente de verdad confirmada
En `/srv/monstruo_dev/docker-compose.yaml` los servicios están definidos con:

```yaml
environment:
  - ENV_FILE=plataforma/ops/env/.env.server.dev
```

Por tanto, ese archivo es la **fuente de verdad efectiva** para variables como:
- `SECRET_KEY`
- `COOKIE_DOMAIN`
- `COOKIE_SECURE`
- `DB_URL`
- y otras variables compartidas de runtime

### Qué significa esto en la práctica
- `ticketera/.env` puede existir
- `gateway/.env` puede no existir
- pero si el contenedor fue levantado con `ENV_FILE=plataforma/ops/env/.env.server.dev`, entonces **ese es el archivo que realmente manda**

### Error de diagnóstico que ocurrió
Durante la depuración se modificó:
- `/srv/monstruo_dev/ticketera/.env`

Pero eso **no resolvía el problema real**, porque los contenedores dev estaban leyendo desde:
- `/srv/monstruo_dev/plataforma/ops/env/.env.server.dev`

Resultado:
- parecía que "ya habíamos corregido COOKIE_SECURE"
- pero en runtime seguía vigente `COOKIE_SECURE=0`
- por eso el problema de sesión persistía

### Causa operativa real del enredo
Había dos archivos que parecían válidos:
1. `ticketera/.env`
2. `plataforma/ops/env/.env.server.dev`

Pero **solo uno estaba siendo usado por Docker Compose**.

Eso creó una falsa sensación de corrección cuando en realidad seguíamos parchando un archivo secundario/no efectivo.

### Regla operativa obligatoria desde ahora
Antes de tocar cualquier variable de entorno en `monstruo_dev`, SIEMPRE verificar primero:

1. qué archivo declara `ENV_FILE` en `docker-compose.yaml`
2. qué archivo está usando realmente el servicio afectado
3. recién después editar el archivo efectivo
4. reiniciar el/los contenedores implicados
5. validar en runtime

### Regla escrita en piedra
**En dev, la configuración efectiva de los contenedores se define primero por `docker-compose.yaml`, no por intuición ni por el `.env` local que parezca más obvio.**

### Cambio real aplicado
Se corrigió el archivo efectivo:
- `/srv/monstruo_dev/plataforma/ops/env/.env.server.dev`

Cambio:
```env
COOKIE_SECURE=0  ->  COOKIE_SECURE=1
```

Luego se reiniciaron:
- `monstruo-dev-gateway`
- `monstruo-dev-ticketera`

### Recomendación de orden futuro
Para evitar que esto vuelva a enredar a cualquiera que lea el proyecto:
- mantener un solo archivo de entorno efectivo por stack dev
- o documentar de forma explícita en `docker-compose.yaml` y en la bitácora cuál es la fuente de verdad
- evitar tener `.env` locales ambiguos si no son realmente consumidos por el runtime

### Conclusión humana y técnica
No, no es que el `.env` esté "dividido" de forma elegante. Más bien había una **fuente real** y otra **aparente**, y eso nos hizo perder tiempo.

La forma correcta de pensarlo es esta:
- `docker-compose.yaml` decide qué archivo entra al runtime
- ese archivo manda
- los demás pueden existir, pero si no están conectados al contenedor, son solo contexto local y pueden confundir

### Segunda aclaración crítica: `ROOT_PATH=/dev` en Gateway dev
Durante la revisión apareció otra fuente real de confusión:

En `/srv/monstruo_dev/docker-compose.yaml`, el servicio `gateway` está levantado con:

```yaml
- ROOT_PATH=/dev
```

Pero el uso observado del sistema fue sobre dominios como:
- `https://login.telconsulting.cl`
- `https://ticketera.telconsulting.cl`

sin usar explícitamente el prefijo `/dev` en la URL final del navegador.

### Por qué esto importa
El `ROOT_PATH` afecta comportamiento de:
- rutas públicas
- redirecciones post-login
- cálculo de `cookie_path`
- compatibilidad entre login, gateway y módulos standalone

En el código actual, tanto Gateway como Ticketera resuelven el path de cookie así:
- si el prefijo detectado es `/dev` → cookie path `/dev`
- si no → cookie path `/`

Eso significa que una mezcla entre:
- gateway configurado con `ROOT_PATH=/dev`
- navegación real sin `/dev`
- módulos en subdominios independientes

puede provocar que la sesión no viaje o no se valide de forma homogénea.

### Regla de diagnóstico nueva
Cuando aparezcan síntomas como:
- `/api/sesion` responde `401: missing_auth`
- el login parece funcionar pero el módulo no reconoce sesión
- el usuario ve partes del shell pero no el menú completo

NO asumir de inmediato que es permisos o DB.

Primero revisar coherencia entre:
1. `COOKIE_DOMAIN`
2. `COOKIE_SECURE`
3. `ROOT_PATH`
4. dominio real usado por el navegador
5. si la URL efectiva usa o no `/dev`

### Sospecha estructural abierta
Puede existir una desalineación entre:
- el modelo dev basado en prefijo (`/dev`)
- y el modelo dev/proxy basado en subdominios (`ticketera.telconsulting.cl`, `login.telconsulting.cl`)

Si ambos se mezclan, el flujo de sesión se vuelve ambiguo.

### Regla escrita para futuro
**No mezclar sin documentar un entorno dev por prefijo (`/dev`) con un entorno dev por subdominios.**

Si el stack va a usar subdominios reales en dev, entonces:
- revisar si `ROOT_PATH=/dev` sigue teniendo sentido
- revisar si login y módulos deben operar con cookie path `/`
- validar todo el flujo con una arquitectura consistente y no híbrida

