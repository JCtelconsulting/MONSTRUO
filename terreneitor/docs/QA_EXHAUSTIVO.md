# QA exhaustivo por navegador — metodología y herramientas

Guía para revisar una app web **de punta a punta con un navegador real**
(no solo curl): cada módulo, cada sección, cada modal/ventana, cada botón, con
datos en **todos los estados** y fotos en **todos los formatos**. Pensado para
reutilizar en otros proyectos (Terreneitor, monstruo, etc.).

> Idea de producto (Juan): a futuro, ofrecer dentro de la app una "ventana con
> Claude" para que el propio usuario reporte/arregle problemas de UI. Esta
> metodología es la base de cómo Claude inspecciona y corrige navegando.

## 1. Por qué navegador y no solo curl

`curl` valida la API (status, JSON) pero **no ejecuta el JavaScript ni renderiza**.
Bugs que SOLO se ven en el navegador y que esta metodología encontró:

- Llamadas/IMG sin el prefijo `/dev` → pegaban a **producción** → login en bucle,
  imágenes rotas, "Acceso denegado".
- `fetchApi` que rebotaba al login con **403** (sin permiso) como si fuera 401.
- Secciones **apiladas** (showSection no ocultaba) y listas que "se comían" la pantalla.
- Imágenes **HEIC** (iPhone) que no se veían (pillow-heif no registrado).
- Markup demo **suelto** fuera de secciones; miniaturas con `path` a la carpeta equivocada.

## 2. Infraestructura de pruebas (sin instalar nada en el host)

Se usa la **imagen oficial de Playwright en Docker** (`mcr.microsoft.com/playwright/
python:v1.49.0-jammy`, ya descargada), con `--network host`. El paquete python se
instala en runtime fijado a `1.49.0` para que calce con el Chromium de la imagen.

Patrón base de cualquier script:

```bash
docker run --rm --network host -v "$PWD:/work" -w /work \
  mcr.microsoft.com/playwright/python:v1.49.0-jammy \
  bash -lc 'pip install -q --break-system-packages "playwright==1.49.0" >/dev/null 2>&1; python3 e2e/<script>.py'
```

Los screenshots quedan en `e2e/shots/` (ignorado por git). Claude los **ve** con
la herramienta Read (renderiza imágenes), que es como juzga "se ve feo".

## 3. Datos de prueba (en TODOS los estados)

```bash
# Reset limpio (borra datos de prod, siembra demo + crea carpetas)
docker exec -i terreneitor-app-dev python - < ops/scripts/qa/seed_dev.py
# Demo COMPLETA: fotos reales con/sin EXIF + tareas en cada estado + proyectos
# activo/pausado/cerrado + informes
bash ops/scripts/qa/demo_flujo_completo.sh
```

Deja asignaciones en: ASIGNADA, EN_PROGRESO, COMPLETADA_TERRENO, PENDIENTE_EXIF
(cuarentena), VALIDADA, RECHAZADA; proyectos ACTIVO/PAUSADO/CERRADO; planes e
informes. Usuarios QA (uno por rol): `qa.dev` / `qa.supervisor` / `qa.gerencia`
/ `qa.terreno` (claves `Qa<Rol>2026!`).

Fotos demo en varios formatos para probar render: JPG (con/sin EXIF), PNG, HEIC.

## 4. Scripts de QA (en `e2e/`)

| Script | Qué hace |
|---|---|
| `test_dev_navegador.py` | Portal: login, detecta loop de redirección, cuenta secciones visibles, errores de consola, screenshot. Da veredicto OK/FALLO. |
| `test_terreno_navegador.py` | Terreno (rol terreno): recorre pestañas y entra a una tarea; verifica que no rebote. |
| `inspeccion_total.py` | Entra a cada módulo con su rol y screenshotea CADA sección, con errores por sección. |
| `explorador_total.py` | EXHAUSTIVO: por módulo/sección abre cada modal **no-destructivo**, detecta imágenes rotas, errores de consola y peticiones fallidas → `e2e/explorador_reporte.json`. |
| `capturar_modales.py` | Captura dirigida de ventanas clave (nuevo usuario/proyecto, estructura, reset clave, upload terreno, lightbox, add-items). |
| `multi_modulos.py` | Verifica que ningún módulo rebote al login. |
| `debug_login.py` / `debug_terreno.py` / `debug_gerencia.py` | Imprimen respuestas de `/api/*`, cookies y navegaciones (para depurar). |

## 5. Reglas de oro (aprendidas a la mala)

1. **Sesión fresca por rol**: `context.clear_cookies()` antes de cada login; si no,
   la página de login redirige por la sesión previa.
2. **NO clickear acciones destructivas/que mutan estado** al explorar: filtrar por
   texto (eliminar/validar/rechazar/pausar/generar…) **y por ícono** (`fa-trash`,
   `fa-pause`, `fa-toggle`, …). Un explorador agresivo dejó 0 proyectos ACTIVO al
   clickear los "pausar". Restaurar con el seed si pasa.
3. **Prefijo de entorno (`/dev`)**: toda URL de API o `<img src>` debe respetarlo.
   En dev sin prefijo pega a prod (cookie rechazada → 404/401/rotas).
4. **403 ≠ 401**: solo 401 (no autenticado) desloguea; 403 (sin permiso) se maneja
   como error normal, nunca rebota al login.
5. **Imágenes "rotas" en modales ocultos** (`<img src="">`) son falsos positivos:
   filtrar por `offsetParent !== null` (visible).
6. **Formatos**: registrar `pillow_heif.register_heif_opener()` y convertir a JPEG
   los formatos que el navegador no muestra (HEIC/TIFF/BMP).

## 6. Hallazgos y arreglos de este pase (2026-06-11)

- **Imágenes por formato**: HEIC no se registraba → fotos de iPhone rotas. + cache
  de thumbnails con ruta hardcodeada de prod (`/srv/terreneitor/...`) → 500 en
  jpg/png/webp. Arreglado (`foto_service` registra HEIF + `to_browser_jpeg`;
  `nucleo.serve_file` deriva el cache de `BASE_FILES_DIR`).
- **Supervisor**: miniaturas/lightbox/visor sin prefijo `/dev` → rotas. Arreglado.
- **Gerencia**: rebote al login por 403; "Acceso denegado" y "Sin archivos" en
  Evidencia; historial que se desbordaba con muchas filas. Arreglado.
- **Portal/Terreno**: login que rebotaba (prefijo y `/auth` sin `/api`),
  secciones apiladas. Arreglado.
- **Modales revisados OK**: nuevo usuario, nuevo proyecto, estructura de proyecto,
  reset de clave (portal); upload de evidencia (terreno); agregar tareas / lightbox
  (supervisor). 0 errores de consola.

## 7. Cómo reusar en otro proyecto

1. Copiar `e2e/` y `ops/scripts/qa/` y ajustar: URLs/subdominios, selectores de
   nav (`data-section`/`data-tab`/`data-target`), lista de secciones y usuarios QA.
2. Adaptar el seed (`seed_dev.py`) al modelo de datos del proyecto.
3. Correr `explorador_total.py` → revisar `explorador_reporte.json` (imágenes rotas
   + errores) y los screenshots `e2e/shots/exp_*`.
4. Arreglar, re-correr, repetir hasta 0 imágenes rotas / 0 errores de consola.
