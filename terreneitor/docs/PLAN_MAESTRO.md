PLAN MAESTRO TERRENEITOR

Proyecto: TERRENEITOR (SaaS Gestión de Obras)
Versión: v3.0 (Enterprise)
Fecha: 2026-02-02
Autoría: Juan + IA
Propósito del documento: Fuente única de verdad. Si el agente propone algo que no calza con esto, se rechaza.

0) Reglas de Juego (Contrato)

---

0.1 Reglas de uso
Este plan manda. Si hay conflicto entre “ideas” y este plan, gana el plan.
Una tarea por ciclo: cada entrega debe terminar un hito verificable.

0.2 Protocolo de trabajo (Ciclo IA)
1. PLAN (lista corta, no ejecutar)
2. CONFIRMACIÓN humana
3. EJECUCIÓN (cambios acotados)
4. VERIFICACIÓN (tests + smoke)
5. CIERRE (bitácora)

0.3 Guardianes "Pixel Perfect"
No se acepta una entrega si:
- Rompe la paridad visual entre módulos (Portal vs Supervisor).
- Introduce deuda técnica (archivos fuera de lugar).
- No verifica funcionalidad offline (PWA).

**REGLA DE ORO DE BACKUPS:**
Los backups NO se guardan dentro del proyecto (`/srv/terreneitor`).
Se deben mover a la carpeta externa `/srv/terreneitor_backups/` para mantener el repositorio limpio.

0.4 Bitácora de avances recientes
- 2026-02-02: Limpieza masiva de repositorio. Estructura `code/`, `ops/`, `docs/` consolidada.
- 2026-02-02: Backups externalizados y logs centralizados.
- 2026-02-02: Limpieza profunda de `data/` (Logs basura, Backups viejos, DBs de prueba eliminadas).
- 2026-02-02: Implementación de caché desarrollo oculto (`/tmp`).
- 2026-02-02: Refinamiento de visualización IA en Supervisor (Badges y Lightbox).
- 2026-02-02: Implementación de Búsqueda Borrosa (Fuzzy Matching) para persistencia de IA ante renombramientos EXIF.

0.5 Mandamientos del Usuario (Reglas de Oro)
1.  **Idioma:** Todo (Respuestas, Código, Logs, Scripts) debe ser en **ESPAÑOL**.
2.  **Bitácora:** Al final de cada sesión, actualizar `PROYECTO_CONTEXTO.md` con:
    -   Fecha/Hora.
    -   Input del Usuario (Literal).
    -   Acción realizada / Respuesta.
    -   Archivos modificados.
3.  **Inicio de Sesión:** Cada nueva conversación debe comenzar con un "LOG DE INICIO DE SESIÓN" en la respuesta.
4.  **Estándar Profesional:** Solo recomendar soluciones de nivel empresarial/profesional. Nada de parches rápidos ("alambritos").
5.  **Rutas Estrictas:**
    -   Scripts $\rightarrow$ `/srv/terreneitor/ops/scripts/[carpeta]/[nombre_espanol.sh]`
    -   Logs $\rightarrow$ `/srv/terreneitor/logs/[nombre_espanol.log]`
6.  **Plan Maestro:** Es la **Fuente Única de Verdad**. Cualquier cambio estructural o de roadmap debe actualizarse primero en `PLAN_MAESTRO.md`. Si el Plan dice X y el código dice Y, el Plan tiene la razón (y el código se corrige).

---

1) Visión y Alcance
1.1 Visión
TERRENEITOR es la plataforma definitiva para la gestión de activos en terreno, integrando evidencia fotográfica, inteligencia artificial y operación offline en un flujo continuo entre Terreno y Gerencia.

1.2 Alcance
- SÍ: Gestión de fotos, AI Vision, Reportes PDF, Offline PWA, RBAC.
- NO: ERP Contable completo (se integra, no se reemplaza), RRHH profundo (solo control básico).

---

2) Principios NO Negociables
2.1 Pixel Perfect
La UI debe ser idéntica en todos los módulos. Nada de "se ve parecido".

2.2 Offline First
La app de Terreno debe funcionar sin internet. La sincronización es transparente.

2.3 Evidencia Inmutable
Las fotos y logs no se borran, se versionan. Trazabilidad total de quién subió qué.

---

3) Estructura de Módulos (Los 4 Pilares)

1. **Terreno (App PWA):**
   - Foco: Velocidad, Offline, Subida de Fotos.
   - Usuarios: Técnicos en campo.
   - Stack: HTML5/JS Vanilla + Service Workers + IndexedDB.

2. **Supervisor (Validación):**
   - Foco: Control de Calidad, Aprobación de fotos, Asignación.
   - Usuarios: Jefes de Terreno.
   - Stack: Escritorio Web.

3. **Gerencia (Dashboard):**
   - Foco: KPIs, Usuarios, Configuración Global.
   - Usuarios: Admins.
   - Stack: Escritorio Web High-Level.

4. **Portal (Cliente):**
   - Foco: Transparencia, solo lectura (o validación final).
   - Usuarios: Clientes Finales.
   - UX: Simplificada, marca blanca.

---

4) Arquitectura Objetivo (Blueprint)

4.1 Backend (Core)
- **Framework:** Python FastAPI (Ligero y rápido).
- **Servidor:** Hypercorn + Anyio.
- **Base de Datos:** SQLite Multi-Tenant (Un archivo .db por proyecto/cliente).
- **Auth:** JWT Stateless.

4.2 IA Engine (Microservicio)
- **Puerto:** 8000 (Producción) / 8081 (Desarrollo).
- **Stack:** PyTorch + YOLOv8 + CUDA.
- **Función:** Analizar fotos en background, RAG sobre documentos.

4.3 Infraestructura Local
- **Hardware:** Lenovo Legion Slim 5 (RTX 4060).
- **Contenedores:** Docker Compose (App + AI + Nginx).
- **Proxy:** Nginx con selector de entorno vía Cookies (`/__env/dev`).
- **Entornos:**
  - **Producción:** `/srv/terreneitor` (Puerto 8080) -> Rama `main`.
  - **Desarrollo:** `/srv/terreneitor_dev` (Puerto 8081) -> Rama `dev`.

4.4 Contrato Operativo Dev/Prod (OBLIGATORIO PARA AGENTES)
- **Fecha de referencia:** 2026-02-11.
- **Proxy inverso oficial:** VM `192.168.60.6` (Nginx). Backend app en `192.168.60.5`.
- **Mapeo de entornos:**
  - `/prod` -> backend `:8080` -> carpeta `/srv/terreneitor` -> rama `main`.
  - `/dev` -> backend `:8081` -> carpeta `/srv/terreneitor_dev` -> rama `dev`.
- **Regla de URL limpia (mandatoria):**
  - La URL visible debe mostrar solo prefijo de entorno: `/prod/...` o `/dev/...`.
  - No se aceptan sufijos de versionado tipo `?v=...` en navegación normal.
- **Comportamiento esperado del switch de entorno:**
  - Producción es el entorno por defecto.
  - El cambio de entorno debe aplicar recarga completa de navegación (sin dejar vista antigua en cache).
  - El entorno seleccionado debe mantenerse en todos los módulos (`portal`, `supervisor`, `terreno`, `gerencia`) hasta cambiar nuevamente.
  - No forzar cierre de sesión como mecanismo normal de switch.
  - Nunca debe quedar en bucle de login/redirección al cambiar entre `/prod` y `/dev`.
- **Prohibido para futuros cambios (NO INVENTAR):**
  - Mezclar entornos por módulo (ejemplo: Portal en `/dev` y Supervisor en `/prod`).
  - Reintroducir query params de versión para “forzar refresh”.
  - Agregar bloqueos por usuario para cambiar de entorno sin requerimiento explícito.
- **Checklist de validación rápida (obligatorio después de tocar routing):**
  1. Entrar sin prefijo y confirmar apertura en `prod` por defecto.
  2. Cambiar a `dev` desde Portal y validar que la URL quede en `/dev`.
  3. Navegar entre módulos y confirmar persistencia del prefijo (`/dev` o `/prod`).
  4. Refrescar navegador y confirmar que no se pierde el entorno seleccionado.
  5. Cerrar sesión y validar que no hay doble login ni bucles.

---

5) Compliance & Seguridad

5.1 Datos
- Retención de fotos según contrato.
- Separación estricta de datos entre clientes (Archivos DB separados).

5.2 Acceso (RBAC)
- Roles duros: `admin`, `supervisor`, `terreno`, `cliente`.
- Middleware de permisos en cada ruta crítica.

---

6) Structure Registry (Estructura Oficial)


/srv/terreneitor/
├── code/                   # Fuente limpia
│   ├── sistema_gestion/    # Backend (Cerebro)
│   │   ├── cerebro.py
│   │   ├── nucleo.py
│   │   └── rutas_*.py
│   ├── static/             # Frontend Modular (Cara)
│   │   ├── modulos/        # (terreno, supervisor, portal...)
│   │   ├── manifest.json
│   │   └── service-worker.js
│   ├── ai_engine/          # IA (Ojos)
│   ├── venv/               # Entorno Virtual
│   └── *.json              # Configs (package, requirements)
├── data/                   # Datos persistentes
│   ├── db/                 # proyectos.db (Única y oficial)
│   ├── files/              # Fotos de obra (Filesystem)
│   ├── cache/              # Thumbnails y ChromaDB
│   ├── locks/              # Seguridad concurrente
│   └── reportes/           # Docs generados
├── docker/                 # Infraestructura unificada
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/                   # Documentación
│   ├── PLAN_MAESTRO.md     # Tu Biblia técnica
│   └── PROYECTO_CONTEXTO.md
├── ops/                    # Operaciones (Scripts)
│   └── scripts/
│       ├── backup/
│       ├── debug/
│       ├── despliegue/
│       ├── herramientas/
│       └── mantenimiento/
└── logs/                   # Historial centralizado


---


7) Roadmap de EPICS (Gating)

### EPIC 01 — Reorganización y Limpieza ✅ (COMPLETADO)
- Estándar de carpetas.
- Externalización de backups.
- Limpieza de root.

### EPIC 02 — Integración IA Vision 🚧 (EN PROGRESO)
- [x] Dockerfile AI.
- [ ] Entrenamiento YOLOv8 Obra.
- [ ] Endpoint `/vision/analyze`.
- [x] UI Feedback en Supervisor y Persistencia Resiliente.

### EPIC 03 — PWA Offline Hardening 📅 (PENDIENTE)
- [ ] Service Worker Cache Strategy V2.
- [ ] Background Sync real.
- [ ] Manejo de conflictos de edición.

### EPIC 04 — Cerebro de Obra (RAG) 📅 (FUTURO)
- [ ] Chatbot técnico con manuales de obra.
- [ ] Búsqueda semántica en PDFs.

### EPIC 05 — Reporting Enterprise 📅 (FUTURO)
- [ ] Export PDF masivo optimizado.
- [ ] Dashboard gerencial v2 (React/Vue componentes aislados si es necesario).
