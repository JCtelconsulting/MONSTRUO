
================================================================================
SESIÓN: 2026-01-24 23:00 - 23:40
================================================================================

## REORGANIZACIÓN COMPLETA - ESTRUCTURA TERRENEITOR

### Objetivo Logrado ✅
Reorganizar completamente la estructura de Monstruo para replicar el modelo profesional de Terreneitor, con naming conventions consistentes, separación de responsabilidades, y UI 100% en español.

### Cambios Realizados

#### 1. Estructura Nueva
```
/srv/monstruo/
├── code/
│   ├── sistema_gestion/  (backend FastAPI)
│   ├── static/           (frontend HTML/CSS/JS)
│   ├── scripts/          (integracion/, mantenimiento/, ai/)
│   └── venv/
├── data/
│   ├── db/               (monstruo.db)
│   ├── logs/
│   ├── backups/
│   └── files/
├── docs/
│   ├── PROYECTO_CONTEXTO.md (este archivo)
│   ├── glosario_ui_es.md
│   └── demo/
└── ops/
    └── scripts/
```

#### 2. Backend Renombrado (Naming Conventions)
- `main.py` / `api_ext.py` → `cerebro.py` (orquestador FastAPI)
- `db.py` → `nucleo.py` (core DB)
- `auth_deps.py` → `dependencias.py` (DI)
- `*_api.py` → `rutas_*.py` (routers: rutas_auth, rutas_workflow, rutas_crm, rutas_bridge, rutas_ai)

#### 3. Imports Actualizados
Todos los archivos backend actualizados para usar nombres nuevos:
- `import nucleo as db`
- `import dependencias as auth_deps`
- `import rutas_workflow`, `import rutas_crm`, etc.

#### 4. UI Normalizada a Español
Archivos traducidos según glosario oficial:
- `workflow.html`: Panel Principal, Flujo de Trabajo, estados (Abierto, En Proceso, Bloqueado, Listo)
- `crm.html`: Empresas, Contactos, botones en español
- `assistant.html` → `asistente.html`: Asistente IA con interfaz completamente en español
- `home.html`, `index.html`: navegación en español

Creado `js/utilidades.js` con mapeo de estados:
```javascript
const MAPEO_ESTADOS = {
    "open": "Abierto",
    "doing": "En Proceso",
    "done": "Listo",
    ...
};
```

#### 5. Scripts Reorganizados
Carpetas semánticas:
- `scripts/integracion/`: sync_laudus*.py, sync_parrotfy*.py (7 archivos)
- `scripts/mantenimiento/`: compute_parrotfy_discrepancies.py (2 archivos)
- `scripts/ai/`: create_parrotfy_workflow_tasks.py (1 archivo)

#### 6. Documentación
- `contexto-IA.md` → `PROYECTO_CONTEXTO.md`
- Creado `glosario_ui_es.md` con términos canónicos UI

### Backup y Rollback
- Backup completo: `/tmp/monstruo_backup_20260124_231151.tar.gz` (36MB)
- Estructura antigua preservada en `/srv/monstruo_old/`

### Verificación
- ✅ Servicio corriendo: uvicorn puerto 8000
- ✅ DB migrada: `/srv/monstruo/data/db/monstruo.db` (692KB)
- ✅ Frontend accesible: 8 archivos HTML
- ✅ Backend funcional: 9 archivos Python
- ✅ Scripts organizados: 10 archivos en carpetas semánticas

### Archivos Modificados
**Backend (9):**
- cerebro.py, nucleo.py, dependencias.py
- rutas_auth.py, rutas_workflow.py, rutas_crm.py, rutas_bridge.py, rutas_ai.py
- workflow_db.py, bridge_init.py

**Frontend (8):**
- workflow.html, crm.html, asistente.html, home.html, index.html
- bridge.html, companies.html, compliance.html

**Scripts (10):**
- integracion/: 7 archivos
- mantenimiento/: 2 archivos
- ai/: 1 archivo

**Utilidades:**
- js/utilidades.js (mapeo estados DB→UI)

### Próximos Pasos
1. Implementar E1: Asistente Operaciones (backend + worker + playbooks)
2. Implementar E2: UI/UX unificada (dashboard hub)
3. Implementar E3: Paquete demo para jefatura

### Tiempo Total
~40 minutos (reorganización completa + normalización UI)

