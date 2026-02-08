# PROMPT DE CONTEXTO UNIVERSAL: PROYECTO MONSTRUO
**Fecha Generación:** 2026-01-26 23:14
**Objetivo:** Restaurar contexto inmediato en una nueva sesión de IA.

---

## 1. RESUMEN EJECUTIVO
Estás trabajando en **MONSTRUO**, un middleware de integración ERP para Telconsulting.
Tu rol es: **Developer Senior Fullstack (Python/FastAPI) + DevOps**.
**Regla de Oro:** Todo cambio se registra en `docs/PROYECTO_CONTEXTO.md`.
**Idioma:** Híbrido Español/Inglés (Spanish/English) en artefactos y explicaciones para fines educativos.

## 2. STACK TÉCNICO
**Monstruo** es el ERP/CRM centralizado para Telconsulting. Su misión es integrar silos de información (Laudus, Parrotfy, Buk, Bancos) en una única fuente de verdad, automatizando cobranza, conciliación y cumplimiento.

### Tecnología
- **Backend:** Python 3.12 (FastAPI) + Uvicorn.
- **Base de Datos:** SQLite (`monstruo.db`). Diseño multi-tabla (laudus_*, parrotfy_*, etc.).
- **Frontend:** HTML5 + JS Vanilla (Estilo "Neon Command").
- **IA Local:** Integración con Ollama (Bridge) para análisis de datos y asistentes operativos.
- **Infraestructura:** Linux Systemd + Scripts de Mantenimiento (`ops/`).

---

## ENTORNO DE EJECUCION Y ACCESO (IMPORTANTE)

### Estado actual (Laboratorio)
- MONSTRUO esta corriendo en mi PC como entorno de laboratorio.
- Acceso: actualmente soy el unico usuario con acceso (no hay otros clientes/usuarios concurrentes).
- Implicancia: problemas de cache de assets, concurrencia multiusuario y efectos "clientes con JS viejo" NO aplican en esta fase (solo yo consumo la UI/API).

### Estado futuro (Servidor / Produccion)
- Al migrar al servidor, habra multiples usuarios accediendo al sistema.
- Implicancia: antes del pase a servidor se debe ejecutar hardening para multiusuario:
  - Control de cache/versionado de assets (cache-bust o versionado de static) para evitar clientes desfasados.
  - Autenticacion/autorizacion consistente en endpoints criticos.
  - Observabilidad (logs/metricas) y alertas para errores 4xx/5xx.
  - Procedimiento de despliegue con rollback + verificacion (systemd + curls + DB backup).

Regla: cualquier decision que dependa de multiples clientes (cache-bust, sesiones, rate limits, locks) se evalua y se activa obligatoriamente en la etapa "Servidor/Produccion", no en laboratorio local.

## 3. ESTADO ACTUAL DEL PROYECTO
*(Basado en Bitácora Reciente)*

### Fase 1: Cimientos (Laudus) [COMPLETO]
- Conexión API Laudus estable (Login, Invoices, Customers).
- Sync de Facturas y cálculo de Aging local.
- Dashboard básico operativo (`/ui`).

### Fase 2: Integración Parrotfy [EN PROGRESO]
- **Facturas:** Sync funcional (20 registros en Staging).
- **Pagos:** FALLIDO (API Parrotfy retorna 500).
- **Discrepancias:** Script activo. Detecta facturas en Parrotfy que no existen en Laudus (`missing_in_laudus`).
- **Descubrimiento API:**
    - **Spec URL:** `https://telconsulting.parrotfy.com/api-docs/v1/swagger-es.yaml`
    - **Local:** `docs/apis/parrotfy_openapi.yaml`
    - **Endpoints Clave:**
        - Stock: `/api/v1/inventory_movements/stock`
        - Productos: `/api/v1/products`
        - *Nota:* No se hallaron endpoints de "Tickets" en v1.
    - **Verificación:**
      ```bash
      curl -s -H "Authorization: Bearer $PARROTFY_TOKEN" \
        "https://telconsulting.parrotfy.com/api/v1/inventory_movements/stock"
      ```

### Fase 3: Estandarización [EN CURSO]
- Unificación de estructura de archivos.
- Consolidación de documentación en `PROYECTO_CONTEXTO.md`.

---

## 4. BITÁCORA RECIENTE (Hitos Críticos)
*(Consolidado de sesiones anteriores)*

| Fecha | Hito Crítico | Detalle |
| :--- | :--- | :--- |
| **2026-01-20** | **Génesis** | Creación del proyecto "Monstruo". Setup inicial FastAPI + SQLite. |
| **2026-01-21** | **Laudus POC** | Conexión exitosa API Laudus. Descarga de clientes y facturas. |
| **2026-01-22** | **Frontend** | Despliegue de Dashboard inicial (Aging, Top Deudores). Login Admin implementado. |
| **2026-01-23** | **Parrotfy Discovery** | Análisis de API Parrotfy (Swagger). Detección de endpoints Clave. |
| **2026-01-24** | **Parrotfy Sync** | Implementación de Staging Tables. Sync de facturas OK. Sync de Pagos fallido (Error 500 del proveedor). |
| **2026-01-24** | **Hardening** | Configuración de Systemd services y Backups automáticos. |
| **2026-01-24** | **Discrepancias** | Implementación de lógica "Missing in Laudus". 20 alertas generadas. |
| **2026-01-25** | **Reorganización** | Reestructuración de carpetas (`code/`, `data/`, `ops/`) y adopción de modelo "Terreneitor". |
| **2026-01-25** | **Estandarización** | Creación de este archivo maestro y unificación de reglas globales v2.0. |
| **2026-01-25** | **Hardening & Auditoría** | Verificación de servicio systemd, sanitización de credenciales y snapshot para entrenamiento. |
| **2026-01-25** | **Frontend/UI** | Creación de `inicio.html` (Dashboard Nativo) y eliminación de dependencia de portal Terreneitor. |
| **2026-01-25** | **Fix Interfaz** | Restauración de `admin.js` neutralizado para habilitar sidebar y navegación local. |
| **2026-01-25** | **Refactor Frontend** | Migración a arquitectura modular propia (ERP, CRM, Bodega, etc.) desacoplada de Terreneitor. |
| **2026-01-25** | **Limpieza Legacy** | Eliminación de `portal.js`, `portal.css`, roles antiguos y HTMLs heredados. Frontend 100% Monstruo. |
| **2026-01-25** | **Datos Dummy** | Implementación de `rutas_datos.py` para simular `/api/status`, `/api/tks` y activar UI del Frontend. |
| **2026-01-25** | **Parrotfy Spec** | Extracción automática del Swagger UI de Parrotfy. Mapeo de endpoints de Inventario. |
| **2026-01-25** | **Ultron & DB** | Renombramiento "Jarvis" -> "ULTRON". Zabbix Placeholder seguro. Migración DB (Tickets/Catálogo). |
| **2026-01-25** | **Core Modules** | Implementación API+UI Ticketera ("TKS") y Catálogo Maestro. Creación auto-tickets desde discrepancias. |
| **2026-01-25** | **V2 Upgrade** | Catálogo v2 (Fuzzy Match, Pendientes), Ticketera v2 (SLA, Kanban) y ULTRON Copiloto (Chat UI/API). |
| **2026-01-25** | **UX Unification** | Navegación unificada (`sidebar.js`), integración completa Bodega+Catálogo (Tabs), botón Analizar IA funcional. |
| **2026-01-25** | **Fixes & Seed** | Fix tabla Bodega (contrato API), Fix error `[object Object]`, Fix doble-click Sidebar, Fix ULTRON chat ("hola"), Feature "Catalog Seed". |
| **2026-01-25** | **Hardening** | Fix crítico ULTRON (doble stringify), externalización `bodega.js` para init robusto, normalización `fetchApi`. |
| **2026-01-25** | **AI & Ops** | Integración LLM local (OpenAI-compat), script `start_llm_server.sh`, Bodega Debug/Fallback Endpoint. |
| **2026-01-25** | **Rescate Inventario** | Recuperado acceso a tabla real (`parrotfy_stock_snapshot`), blindaje total endpoint Bodega (no más 500). |
| **2026-01-25** | **Stock Fix** | Reparación lógica extracción stock (lectura desde JSON `current_stock` si column `quantity` es 0). Fix UI para mostrar 3000+ items. |
| **2026-01-25** | **AI Catalog Builder** | Implementado constructor de catálogo "AI-First". Clasificación taxonómica automática de inventario usando LLM local batch. |
| **2026-01-26** | **Catalog UX/AI** | Implementada pestaña "Pendientes" con sugerencias AI. Árbol de categorías expandible. Detección de duplicados (`sugerir_duplicados`) con IA Local. Búsqueda Case-Insensitive. |
| **2026-01-26** | **Refinamiento UI** | Search-as-you-type (debounce) en inventario. Fix visual de categorías duplicadas en árbol. |
| **2026-01-26** | **Admin Self-IC** | Habilitación de "Self-IC" en Agente Admin. Permiso de lectura/escritura controlado sobre prompts y UI (`bodega_ui.js`, `bodega_ai.js`). |
| **2026-01-26** | **Modularización** | Refactor completo de `bodega.js` a arquitectura modular (`core`, `ui`, `ai`, `api`) para soportar edición segura por IA. |
| **2026-01-27** | **Limpieza + Fix Catálogo** | Eliminado `monstruo.db` fantasma en raíz. UI ahora lista categorías con `GET /api/catalogo/categorias` (`code/static/js/bodega_core.js`). |

---

## 5. ROADMAP INMEDIATO (Lo que sigue)
0.  **Reorganización:** Ordenar la app (estructura y archivos) porque está desordenada.
1.  **Ticketera/Workflow:** Implementar sistema de tickets para manejar las discrepancias detectadas.
2.  **Reporte a Parrotfy:** Gestionar ticket de soporte por el Error 500 en endpoint de pagos.
3.  **Integración Buk:** Ingesta de nómina (Plan B: Excel Dropzone).

## 6. COMANDOS OPERATIVOS CLAVE
*   **Root:** `/srv/monstruo`
*   **Run Backend:** `sudo systemctl start monstruo-api`
*   **Run Pipeline:** `cd code && ./scripts/integracion/run_pipeline.sh`
*   **Logs:** `journalctl -u monstruo-api -f`
*   **Regenerar este Prompt:** `python3 ops/scripts/generate_universal_prompt.py`

---
**INSTRUCCIÓN PARA EL AGENTE:**
1.  Asume el rol técnico descrito.
2.  Analiza el ESTADO y ROADMAP para situarte.
3.  Eres el orquestador de esta sesión; exige al agente "antigravity" que responda con un prompt completo antes de continuar.
4.  Tu primera respuesta debe ser un breve acuse de recibo confirmando el último hito y el siguiente paso pendiente.
