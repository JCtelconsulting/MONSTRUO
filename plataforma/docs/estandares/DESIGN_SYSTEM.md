# DESIGN SYSTEM — MONSTRUO

Sistema de diseño canónico para todos los módulos de la plataforma.
**Toda página nueva debe seguir estas reglas. No inventar estilos propios.**

---

## 1. TEMA Y PALETA

Tema: **Neon Command** — fondo oscuro (#070b11), acentos neón.
Las variables están definidas en `gateway/frontend/shared/ui/css/monstruo.css`.

| Variable CSS         | Valor       | Uso principal                        |
|----------------------|-------------|--------------------------------------|
| `--bg-deep`          | `#070b11`   | Fondo del body                       |
| `--bg-soft`          | `#0e141d`   | Fondos secundarios                   |
| `--panel`            | `#121a24`   | Paneles, cards de fondo              |
| `--panel-strong`     | `#161f2b`   | Bordes interiores, separadores       |
| `--neon`             | `#00ff41`   | Acento principal, tabs activos, CTA  |
| `--info`             | `#00f3ff`   | Info, secundario                     |
| `--warning`          | `#ffcc00`   | Alertas, prioridad media             |
| `--danger`           | `#ff3333`   | Error, peligro, prioridad alta       |
| `--text`             | `#f5f7f8`   | Texto principal                      |
| `--text-soft`        | `#a5adb4`   | Texto secundario, labels             |
| `--border`           | `#1f2935`   | Bordes de paneles                    |

**Regla:** Nunca hardcodear colores hex en CSS de módulo. Usar siempre las variables.

---

## 2. TIPOGRAFÍA

- Fuente: **Space Grotesk** (Google Fonts, weights 400/500/600/700)
- Font-size base: `12px` (definido en `:root`)
- Escala relativa: usar `rem` (1rem = 12px base)

| Uso                        | Tamaño         | Weight | Notas                          |
|----------------------------|----------------|--------|--------------------------------|
| Título de módulo           | `1.8rem`       | 800    | `.module-page-title`           |
| Subtítulo                  | `0.9rem`       | 400    | `.module-shell-subtitle`       |
| Título de sección          | `1.1rem`       | 700    | `.section-header h3`           |
| Labels / uppercase         | `0.75–0.8rem`  | 800    | `text-transform: uppercase`    |
| Cuerpo de tabla            | `0.9rem`       | 500    |                                |
| Texto secundario           | `0.85rem`      | 400    | color: `var(--text-soft)`      |

---

## 3. ESTRUCTURA HTML ESTÁNDAR DE MÓDULO

```html
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>NOMBRE_MODULO | Monstruo</title>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="shared/css/monstruo.css?v=75" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <link rel="stylesheet" href="css/MODULO.css?v=1" />
</head>

<body class="sidebar-collapsed MODULO-shell" data-current-module="MODULO_ID">
    <header id="app-header">
        <div class="header-top">
            <h1>MONSTRUO</h1>
            <button id="sidebar-toggle" class="btn-icon"><i class="fas fa-bars"></i></button>
        </div>
        <nav id="dynamic-sidebar" class="side-nav"></nav>
        <div class="header-actions">
            <span id="who" class="pill shell-who-pill">Usuario</span>
            <div class="footer-buttons-container">
                <button id="btn-open-change-password" class="btn-account" title="Cambiar Contraseña">
                    <i class="fas fa-key"></i> <span>Cuenta</span>
                </button>
                <button id="btnLogout" class="btn-logout" title="Cerrar Sesión">
                    <i class="fas fa-sign-out-alt"></i> <span>Salir</span>
                </button>
            </div>
        </div>
    </header>

    <main>
        <div class="main-inner module-shell">
            <!-- ENCABEZADO DEL MÓDULO -->
            <div class="section-header module-tabs-header module-shell-header">
                <div class="module-shell-title">
                    <h2 class="module-page-title">Nombre del Módulo</h2>
                    <p class="module-shell-subtitle">Descripción breve</p>
                </div>
                <div class="module-shell-actions">
                    <!-- Botones de acción global del módulo (ej: Nueva Tarea) -->
                </div>
            </div>

            <!-- PESTAÑAS -->
            <div class="tab-bar">
                <button class="tab-btn active" data-tab="tab1" onclick="loadTab('tab1', this)">
                    <i class="fas fa-icon"></i> Etiqueta
                </button>
                <!-- más tabs... -->
            </div>

            <!-- CONTENIDO DE TABS -->
            <section class="section-block module-shell-content module-shell-content-fill">
                <div id="tab-content" style="flex:1; overflow:hidden; display:flex; flex-direction:column;"></div>
            </section>
        </div>
    </main>

    <!-- Scripts compartidos — SIEMPRE en este orden -->
    <script src="shared/js/utilidades.js?v=210"></script>
    <script src="shared/js/admin.js?v=5"></script>
    <script src="shared/js/sidebar.js?v=88"></script>
    <!-- Scripts propios del módulo -->
    <script src="js/MODULO_api.js?v=1"></script>
    <script src="js/MODULO_ui.js?v=1"></script>
    <script src="js/MODULO_main.js?v=1"></script>
</body>
</html>
```

---

## 4. PESTAÑAS (TAB BAR) — ESTÁNDAR CANÓNICO

**El bloque header + tabs + contenido es UNA UNIDAD.** No separar con líneas en blanco ni comentarios entre los tres elementos hermanos. La cadena exacta de hermanos dentro de `.main-inner.module-shell` debe ser:

```text
.section-header.module-tabs-header.module-shell-header
.tab-bar
.section-block.module-shell-content
```

### Estructura literal (copiar tal cual)

```html
<main>
    <div class="main-inner module-shell">
        <div class="section-header module-tabs-header module-shell-header">
            <div class="module-shell-title">
                <h2 class="module-page-title">Nombre del Módulo</h2>
                <p class="module-shell-subtitle">Descripción breve</p>
            </div>
            <div class="module-shell-actions">
                <!-- botones de acción global -->
            </div>
        </div>

        <!-- TAB BAR -->
        <div class="tab-bar">
            <button class="tab-btn active" data-tab="nombre" onclick="loadTab('nombre', this)">
                <i class="fas fa-icon"></i> Etiqueta
            </button>
        </div>

        <section class="section-block module-shell-content">
            <!-- CONTENIDO DINÁMICO -->
            <div id="tab-content"></div>
        </section>
    </div>
</main>
```

### Reglas no negociables

1. **NO** poner líneas en blanco ni comentarios entre `</div class="...module-shell-header">` y `<div class="tab-bar">`. El selector que aplica el espaciado correcto es `.module-tabs-header + .tab-bar` (combinador adyacente). Si los separas con un comentario HTML como `<!-- TABS -->` el combinador SIGUE funcionando porque los comentarios HTML no rompen la adyacencia, pero **un nodo elemento intermedio sí la rompe**. Mantener los comentarios solo encima del bloque, nunca como hermano elemento.
2. **NO** agregar la clase `module-shell-content-fill` a menos que el módulo necesite que el contenido ocupe altura completa con flex column (drawer fullscreen, kanban). Ticketera, GTA, ERP y PMO usan **solo** `module-shell-content`.
3. **NO** poner `style="flex:1; overflow:auto; display:flex; flex-direction:column"` inline en `#tab-content`. Esos estilos no van — el contenedor se rige por el flujo natural.
4. **NO** redefinir `.tab-bar` ni `.tab-btn` en el CSS del módulo. Si necesitas variantes específicas, crea una clase scope (`.tks-tab-bar`, `.gta-tab-bar`) y SOLO modifica color de acento o iconografía.

### Medidas exactas (vienen del CSS global, NO redefinir)

| Selector | Propiedad | Valor |
|---|---|---|
| `.module-tabs-header` | `min-height` | `56px` |
| `.module-tabs-header` | `margin-bottom` | `10px` |
| `.module-tabs-header` | `padding-bottom` | `0` |
| `.module-tabs-header + .tab-bar` | `margin-top` | `0` |
| `.module-tabs-header + .tab-bar` | `padding-bottom` | `8px` |
| `.module-tabs-header + .tab-bar > .tab-btn` | `min-height` | `34px` |
| `.module-tabs-header + .tab-bar > .tab-btn` | `min-width` | `86px` |
| `.module-tabs-header + .tab-bar > .tab-btn` | `padding` | `0 10px` |
| `.module-tabs-header + .tab-bar > .tab-btn` | `font-size` | `0.8rem` |
| `.tab-bar` (base) | `gap` | `0.8rem` |
| `.tab-bar` (base) | `border-bottom` | `1px solid rgba(255,255,255,0.1)` |
| `.tab-bar` (base) | `margin-bottom` | `16px` |
| `.tab-bar` (base) | `padding` | `0 4px 10px` |

### Iconografía dentro de tab-btn

Usar **siempre** Font Awesome dentro de las pestañas — NO emojis Unicode. Patrón:

```html
<button class="tab-btn active" data-tab="dashboard">
    <i class="fas fa-chart-line"></i> Resumen
</button>
```

- Tab activo: clase `active`, color `--neon`, fondo translúcido pill
- Tab inactivo: color `--text-soft`
- **NO usar** `border-bottom: 2px solid` manual ni `::after` underline — el estilo activo lo da el CSS global

---

## 5. BOTONES

### Jerarquía visual

| Clase           | Uso                      | Estilo                                    |
|-----------------|--------------------------|-------------------------------------------|
| `.btn-primary`  | Acción principal         | Gradiente neon→info, texto oscuro         |
| `.btn-secondary`| Acción secundaria        | Fondo oscuro, borde blanco suave          |
| `.btn-danger`   | Eliminar / acción riesgosa | Borde rojo, hover fondo rojo            |
| `.btn-sm`       | Acciones en tabla/card   | Compacto, borde gris, hover blanco       |

**Regla:** Botones de formulario y CTA usan `.btn-primary`. Acciones contextuales en tablas usan `.btn-sm`. Nunca `btn-principal`, `btn-info`, `btn-peligro` (nombres legacy — en desuso).

```html
<button class="btn-primary"><i class="fas fa-plus"></i> Acción Principal</button>
<button class="btn-secondary">Cancelar</button>
<button class="btn-sm btn-danger"><i class="fas fa-trash"></i></button>
```

---

## 6. TABLAS

Usar la clase `.monstruo-table` (estándar definido en monstruo.css):

```html
<div class="table-scroll">
    <table class="monstruo-table">
        <thead>
            <tr>
                <th>Columna</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Valor</td>
            </tr>
        </tbody>
    </table>
</div>
```

- `thead th`: uppercase, 0.74rem, weight 800, color `rgba(228,236,244,0.8)`
- `tbody td`: fondo `rgba(18,26,36,0.92)`, radio en primera/última columna
- Envolver siempre en `.table-scroll` para overflow horizontal

**NO usar** `.user-table` ni `.erp-table` en módulos nuevos — son legacy.

---

## 7. FORMULARIOS E INPUTS

Clase estándar: `.input-dark`

```html
<div class="field">
    <label>Nombre del campo</label>
    <input type="text" class="input-dark" placeholder="...">
</div>
```

- Fondo: `rgba(6,10,14,0.88)`, borde `rgba(255,255,255,0.14)`
- Focus: borde `rgba(0,255,65,0.5)` + glow verde suave
- `min-height: 38px`
- Labels: uppercase, 0.8rem, weight 700, color blanco

Grid de formulario:
```html
<div class="form-grid-4"> <!-- 2 columnas en desktop, 1 en móvil -->
    <div class="field">...</div>
    <div class="field">...</div>
</div>
```

---

## 8. MODALES / DIÁLOGOS

Usar `.modal-backdrop` + `.modal-content` del CSS global. Para modales más simples, usar `<dialog>` nativo con el estilo del bloque PMO/ERP:

```html
<div class="modal-backdrop" id="modal-xxx" style="display:none;">
    <div class="modal-content">
        <div class="modal-header">
            <h2>Título del Modal</h2>
            <button class="modal-close-btn" onclick="cerrarModal()">×</button>
        </div>
        <div class="modal-body">
            <!-- contenido -->
        </div>
        <div class="modal-footer">
            <button class="btn-secondary" onclick="cerrarModal()">Cancelar</button>
            <button class="btn-primary" onclick="guardar()">Guardar</button>
        </div>
    </div>
</div>
```

- Fondo: `backdrop-filter: blur(12px)` + `rgba(0,0,0,0.6)`
- Card: gradiente oscuro, borde `rgba(255,255,255,0.12)`, `border-radius: 16px`

---

## 9. CARDS / KPI

Para métricas y stats:
```html
<div class="kpi-row">
    <div class="kpi-card">
        <div class="kpi-val">42</div>
        <div class="kpi-lbl">Tareas Activas</div>
    </div>
</div>
```

Para cards de navegación o acceso rápido:
```html
<div class="gate">
    <a href="#" class="card card-terreno">
        <i class="fas fa-icon"></i>
        <h2>Título</h2>
        <p>Descripción breve</p>
    </a>
</div>
```

Variantes de acento de card: `.card-terreno` (neon), `.card-supervisor` (info), `.card-gerencia` (warning)

---

## 10. BADGES / ESTADO

Usar chips inline para estados:

```html
<!-- Estados semánticos -->
<span class="tarea-tag prioridad-alta">Alta</span>    <!-- rojo -->
<span class="tarea-tag prioridad-media">Media</span>  <!-- amarillo -->
<span class="tarea-tag prioridad-baja">Baja</span>    <!-- verde -->
<span class="tarea-tag">Neutro</span>                 <!-- gris -->
```

Para live status (dashboard):
```html
<div class="intro-status">
    <div class="live-dot"></div>
    <div>
        <div class="status-label">Estado</div>
        <div class="status-value">Activo</div>
    </div>
</div>
```

---

## 11. ESTRUCTURA DE ARCHIVOS POR MÓDULO

**Regla:** La carpeta de frontend se llama siempre `ui/` — nunca `frontend/` ni otro nombre.

```
MODULO/
├── Dockerfile               # Imagen del contenedor — copia ticketera/Dockerfile
├── requirements.txt         # Dependencias Python — copia ticketera/requirements.txt
├── __init__.py
├── main.py                  # FastAPI app — entry point del contenedor
│
├── ui/                      # Frontend ← SIEMPRE "ui/", nunca "frontend/"
│   ├── MODULO.html          # Entry point HTML — sigue la plantilla de sección 3
│   ├── css/
│   │   └── MODULO.css       # Estilos propios (NO redefinir variables globales)
│   ├── js/
│   │   ├── MODULO_api.js    # Wrapper fetchApi para /api/MODULO/*
│   │   ├── MODULO_ui.js     # Helpers de renderizado HTML
│   │   └── MODULO_main.js   # Controlador principal
│   └── TAB/                 # Una subcarpeta por pestaña (si el módulo tiene tabs)
│       ├── TAB.html
│       ├── TAB.css
│       └── TAB.js
│
├── backend/                 # Lógica de negocio y API
│   ├── __init__.py
│   ├── router.py            # APIRouter con prefix="/api/MODULO"
│   ├── models.py            # Modelos Pydantic (Create, Update, Response)
│   └── service.py           # Lógica compleja extraída del router (opcional)
│
├── migrations/              # SQL versionado — un archivo por cambio de schema
│   ├── README.md            # Instrucciones de ejecución
│   └── 001_initial.sql      # NNN_descripcion.sql — nunca modificar ya ejecutados
│
├── tests/                   # Tests de integración y unitarios
│   ├── __init__.py
│   ├── conftest.py          # Fixtures compartidas (db_conn, cliente HTTP, etc.)
│   └── test_ENTIDAD.py      # Un archivo por entidad o flujo principal
│
├── scripts/                 # Utilidades de administración y datos
│   ├── README.md            # Qué hace cada script y cómo ejecutarlo
│   ├── seed_*.py            # Datos de prueba y datos iniciales
│   └── fix_*.py             # Correcciones puntuales de datos
│
├── docs/                    # Documentación técnica del módulo
│   └── README.md            # Descripción, API, decisiones de diseño
│
└── data/                    # Archivos de datos locales del módulo
    └── .gitkeep             # No subir datos sensibles ni CSVs de producción
```

### Propósito de cada carpeta

| Carpeta | Qué va ahí | Qué NO va ahí |
| ------- | ---------- | ------------- |
| `ui/` | HTML, CSS, JS del frontend | Lógica de negocio, datos |
| `backend/` | Router FastAPI, modelos Pydantic, servicios | Archivos estáticos |
| `migrations/` | Archivos `.sql` numerados para cambios de schema | Migraciones ya ejecutadas modificadas |
| `tests/` | `test_*.py` con pytest, fixtures en `conftest.py` | Datos de producción, scripts de admin |
| `scripts/` | Seeds, exportaciones, correcciones puntuales | Tests, lógica de negocio |
| `docs/` | README del módulo, decisiones de diseño, diagramas | Código, datos |
| `data/` | Archivos locales del módulo (CSVs temporales, caches) | Credenciales, `.env` |

### Estado actual de cada app (referencia)

| App | Puerto | Backend | UI | Notas |
| --- | ------ | ------- | -- | ----- |
| **gateway** | 9001 | `backend/` | `ui/` | Sidebar, login, dashboard, proxy central |
| **ticketera** | 9005 | `backend/` | `ui/` | Multi-tab. Jobs en `backend/jobs/` |
| **fundacion** | 9006 | `backend/` | `ui/` | CRUD simple + proxy a gateway |
| **bodega** | 9007 | `backend/` | `ui/` | WMS — inventario, catálogo, stock |
| **crm** | 9008 | `backend/` | `ui/` | Clientes, interacciones, cuenta corriente |
| **erp** | 9009 | `backend/` | `ui/` | Facturación, cobranza, integración Laudus |
| **pmo** | 9010 | `backend/` | `ui/` | Pendiente de desarrollo |
| **ia** | 9011 | `backend/` | `ui/` | Pendiente de desarrollo |
| **gta** | 9012 | `backend/` | `ui/` | Gestión de tareas automatizada |
| **zabbix** | 9013 | `backend/` | `ui/` | Proxy monitoreo infraestructura |

---

## 12. CÓMO AGREGAR UN MÓDULO NUEVO

Tocar **5 lugares** en este orden:

1. **Crear carpeta** `MODULO/` con la estructura de la sección 11.

2. **`docker-compose.yaml`** — agregar el servicio:

   ```yaml
   MODULO:
     build:
       context: .
       dockerfile: ./MODULO/Dockerfile
     container_name: ${STACK_NAME:-monstruo-dev}-MODULO
     env_file:
       - ${ENV_FILE:-plataforma/ops/env/.env.server.dev}
     ports:
       - "${MODULO_PORT:-PUERTO}:PUERTO"
     environment:
       - PYTHONPATH=/app:/app/plataforma
       - PORT=PUERTO
       - DB_URL=postgresql://...
     depends_on:
       - db
     restart: unless-stopped
     command: ["uvicorn", "MODULO.backend.main:app", "--host", "0.0.0.0", "--port", "PUERTO"]
   ```

3. **`gateway/ui/shared/ui/js/sidebar.js`** — agregar en ambos arrays (prod y dev):
   ```js
   // prod:
   { id: 'MODULO', label: 'Nombre', icon: 'fas fa-icon', link: `https://MODULO.telconsulting.cl${envPrefix}/`, title: 'Descripción' }
   // dev:
   { id: 'MODULO', label: 'Nombre', icon: 'fas fa-icon', link: localServiceUrl(PUERTO, '/'), title: 'Descripción' }
   ```

4. **`plataforma/core/config.py`** — agregar en:
   - `UI_MODULES`: `{"id": "MODULO", "label": "Nombre"}`
   - `PERMISSION_TO_MODULE_MAP`: `"MODULO": "MODULO"`
   - `ROLE_PERMISSIONS`: permisos `MODULO:read` / `MODULO:write` a los roles que corresponda

5. **`gateway/backend/main.py`** — agregar en:
   - `SERVICES_MAP`: `"MODULO": f"http://MODULO:{os.getenv('MODULO_PORT', 'PUERTO')}"`
   - `SERVICE_API_PREFIX`: `"MODULO": "MODULO"`
   - Ruta de redirección `/MODULO` y `/MODULO/` si el módulo no tiene subdominio propio

### Puertos asignados

| Puerto | Servicio | Variable de entorno |
| ------ | -------- | ------------------- |
| 9001 | gateway | `GATEWAY_PORT` |
| 9005 | ticketera | `TICKETERA_PORT` |
| 9006 | fundacion | `FUNDACION_PORT` |
| 9007 | bodega | `BODEGA_PORT` |
| 9008 | crm | `CRM_PORT` |
| 9009 | erp | `ERP_PORT` |
| 9010 | pmo | `PMO_PORT` |
| 9011 | ia | `IA_PORT` |
| 9012 | gta | `GTA_PORT` |
| 9013 | zabbix | `ZABBIX_PORT` |

---

## 13. ANTIPATRONES — NO HACER

| Antipatrón | Corrección |
| ---------- | ---------- |
| Carpeta `frontend/` en vez de `ui/` | Siempre `ui/` |
| `main.py` y `router.py` sueltos en raíz del módulo | Mover a `backend/` al tocar el archivo |
| Inline styles para colores (`color:#ff0`) | Usar variables CSS |
| `background: #1a1f2b` hardcodeado | Usar `var(--panel)` o `var(--bg-soft)` |
| Tabs con `border-bottom: 2px solid` manual | Usar `.tab-bar > .tab-btn` estándar |
| Modales con estilos inline | Usar `.modal-content` del CSS global |
| `<table>` sin `.table-scroll` | Siempre envolver en `.table-scroll` |
| `.user-table`, `.erp-table` en módulos nuevos | Usar `.monstruo-table` |
| `btn-principal`, `btn-info`, `btn-peligro` | Usar `btn-primary`, `btn-secondary`, `btn-danger` |
| CSS de módulo redefine `--neon` u otras vars | No redefinir variables globales |
| Scripts en `<head>` | Scripts siempre al final del `<body>` |
| Módulo nuevo sin entrada en docker-compose | Seguir el checklist de sección 12 completo |

---

## 14. RESPONSIVO

El CSS global maneja breakpoints en `@media (max-width: 900px)` y `@media (max-width: 768px)`.
En móvil el sidebar se convierte en barra superior de iconos.

En CSS de módulo solo agregar responsive para componentes propios si el layout base no es suficiente.
Nunca sobreescribir `header`, `main`, `body` en CSS de módulo.

---

*Última actualización: 2026-04-30 — aplica a todos los módulos desde GTA en adelante.*
