# Pruebas de navegador (E2E con Playwright) — entorno DEV

Pruebas de UI **reales** (un navegador Chromium de verdad) contra el entorno de
desarrollo. Detectan cosas que `curl` no ve: loops de redirección, secciones
apiladas, llamadas a la API que se van al entorno equivocado, errores de consola
y peticiones 404/500 en segundo plano.

## Por qué existen

`curl` valida la API (status 200, JSON correcto) pero **no ejecuta el JavaScript**.
Varios bugs solo aparecen al correr el front:

- `fetchApi` sin el prefijo `/dev` → las llamadas pegaban a **producción** y el
  portal rebotaba al login (`?reason=expired`).
- En **terreno**, `fetchApi('/auth/whoami')` se mapeaba a `/dev/auth/whoami`
  (sin `/api`) → **404** → `handleAuthExpired()` → "vuelve atrás" al login.
- El portal mostraba **todas las secciones apiladas** (el `showSection` no
  ocultaba las demás) y un bloque demo suelto.

- **Gerencia** rebotaba al login: llamaba endpoints de supervisor que dan **403**
  a GERENCIA y `fetchApi` trataba el 403 como sesión caída. Fix: rebotar solo en
  401; 403 se maneja como error normal. Además se le dieron a gerencia endpoints
  propios de lectura (evidencia/cuarentena/archivos) bajo `/api/gerencia/...`.
- **Supervisor**: 403 ruidoso por intentar `/api/admin/proyectos` (admin-only) y
  "Sin resultados" en proyectos porque la vista exige que la **carpeta del
  proyecto exista en disco** (faltaba al sembrar datos de prueba).

Todos se encontraron y se confirmaron arreglados con la inspección visual.

## Resetear / sembrar datos de DEV

Dev NO debe tener datos reales de producción. Para borrar todo y sembrar datos
de prueba (4 usuarios uno por rol, 4 proyectos demo, items, un plan y
asignaciones con estados variados) + crear sus carpetas en disco:

```bash
docker exec -i terreneitor-app-dev python - < ops/scripts/qa/seed_dev.py
```

El script aborta si `ENV=production` (salvaguarda). Tras sembrar, supervisor ve
los proyectos solo si existen sus carpetas (el propio script las crea).

## Cómo correr

No hay que instalar nada en el host: se usa la **imagen oficial de Playwright en
Docker** (ya descargada) con `--network host`. El paquete python de Playwright se
instala en runtime fijado a `1.49.0` para que calce con el Chromium de la imagen.

```bash
# Portal (login + loop + secciones + screenshot)
bash ops/scripts/qa/correr_pruebas_navegador.sh

# Módulo terreno (login rol terreno + 3 pestañas + entrar a una tarea)
docker run --rm --network host -v "$PWD:/work" -w /work \
  -e QA_EMAIL=qa.terreno@telconsulting.cl -e QA_PASS='QaTerr2026!' \
  mcr.microsoft.com/playwright/python:v1.49.0-jammy \
  bash -lc 'pip install -q --break-system-packages "playwright==1.49.0" >/dev/null 2>&1; python3 e2e/test_terreno_navegador.py'
```

Cada prueba imprime un veredicto `RESULTADO ... OK ✅ / FALLO ❌` y guarda
screenshots en `e2e/shots/` (ignorados por git) para revisión visual.

## Archivos

| Archivo | Qué hace |
|---|---|
| `e2e/test_dev_navegador.py` | Portal: login, detecta loop, cuenta secciones visibles, errores de consola, screenshot |
| `e2e/test_terreno_navegador.py` | Terreno: login rol terreno, recorre pestañas, entra a una tarea, verifica que no rebote |
| `e2e/multi_modulos.py` | Carga portal/supervisor/gerencia/terreno y verifica que ninguno rebote |
| `e2e/inspeccion_total.py` | Inspección visual TOTAL: entra a cada módulo con su rol y screenshotea CADA sección/pestaña, registrando errores por sección |
| `ops/scripts/qa/seed_dev.py` | Borra datos de prod y siembra datos de prueba + carpetas |
| `e2e/debug_login.py`, `e2e/debug_terreno.py` | Debug: imprimen respuestas de `/api/*`, cookies y navegaciones |
| `ops/scripts/qa/correr_pruebas_navegador.sh` | Runner del test de portal |

## Usuarios de QA (solo en la BD de DEV)

| Usuario | Clave | Rol | Uso |
|---|---|---|---|
| `qa.dev@telconsulting.cl` | `QaDev2026!` | ADMIN | Portal / supervisor / gerencia |
| `qa.terreno@telconsulting.cl` | `QaTerr2026!` | TERRENO | Módulo terreno (enlazado a tareas de planes ABIERTO) |

> Son cuentas de prueba; no existen en producción. Borrar si no se quieren.

## Regla de trabajo

Tras **cualquier** cambio de frontend o de autenticación en dev: correr la prueba
del módulo afectado y **mirar el screenshot + el veredicto** antes de dar el
cambio por terminado.
