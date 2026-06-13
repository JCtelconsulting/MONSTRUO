# Plan: alinear Terreneitor al modelo de módulo Monstruo

> **Para quién:** el agente (Fable) que ejecute esta re-arquitectura.
> **Autor del plan:** sesión Opus 2026-06-13. **Estado:** PENDIENTE de ejecución.
> **Tamaño:** grande — toca packaging Python, build, runtime, serving y rutas de assets.

## 0. Objetivo

Convertir Terreneitor de **app autocontenida** (como venía del repo standalone) a
**módulo integrado del monorepo**, con la misma forma que `bodega/`, `crm/`, `erp/`,
`fundacion/`, etc.

## 1. Diferencia de fondo (estado actual vs objetivo)

| Aspecto | Módulo estándar (bodega) | Terreneitor HOY | Objetivo |
|---|---|---|---|
| Imports | `plataforma.core.*` + `bodega.backend.*` | `backend.*` (aislado, NO usa `plataforma.core`) | `terreneitor.backend.*` + `plataforma.core.*` |
| Entry | `uvicorn bodega.backend.main:app` | `python -m backend.core.cerebro` | `uvicorn terreneitor.backend.main:app` |
| Contenedor | `COPY . /app` (todo el repo) | `COPY ./backend ./frontend` (aislado) | `COPY . /app` |
| UI | `ui/` | `frontend/` | `ui/` |
| Dockerfile | raíz del módulo | `docker/Dockerfile` | raíz del módulo |
| Scripts | `scripts/` | `ops/scripts/` (+ `ops/environments/.env`) | `scripts/` |
| Tests | `tests/` | `e2e/` + `backend/tests/` | `tests/` |
| Migraciones | `migrations/` | `backend/migrations/` | `migrations/` |
| Deps | `requirements.txt` (raíz módulo) | `backend/requirements.txt` + `pyproject.toml` propio | `requirements.txt` (raíz módulo) |
| `__init__.py` raíz | sí | no | sí |

App real: `terreneitor/backend/core/nucleo.py` define `app = FastAPI(...)`;
`backend/core/cerebro.py` lo importa, agrega middleware/routers y corre uvicorn.

## 2. Cuidados NO negociables

1. **Solo rama `dev`.** PROD de Terreneitor **sigue corriendo standalone en 60.5** (no
   migrado). Esta re-arquitectura **diverge** del repo standalone `/srv/terreneitor_dev`;
   coordinarlo con la migración a PROD (ver `MIGRACION_MONSTRUO.md`). No tocar PROD.
2. **Verificación obligatoria en navegador** tras cada fase con riesgo de runtime
   (metodología: `terreneitor/docs/PRUEBAS_NAVEGADOR.md` / Playwright en Docker). Los 6
   destinos: hub, login, terreno, supervisor, gerencia, portal + SSO del gateway.
3. **Rebuild** con `./plataforma/ops/scripts/dev-rebuild.sh terreneitor` tras cambios de
   código; `curl /health` (puerto 8005) y de cada módulo antes de declarar OK.
4. **No `git add -A`**: paths explícitos. Commits granulares por fase.
5. No editar `auth.users` sin OK del dueño. No subir `plataforma/ops/secrets/`.
6. El proxy `/shared/*` del gateway (`cerebro.py:167`) ya se usa para assets comunes;
   `offline-store.js` ya está deduplicado vía ese proxy — no reintroducir copias.

## 3. Fases (en orden; commit + verificación por fase)

### Fase A — Repackaging Python (`backend.*` → `terreneitor.backend.*`)
- Crear `terreneitor/__init__.py`.
- Reescribir TODOS los imports `from backend.` / `import backend.` →
  `from terreneitor.backend.` (≈60 ocurrencias; barrer con grep, revisar uno a uno).
- Renombrar el entrypoint: consolidar `backend/core/{nucleo,cerebro}.py` en
  `backend/main.py` que exponga `app` (manteniendo el orden de middleware/routers actual).
- Verificación: `python -c "import terreneitor.backend.main"` desde la raíz del repo sin error.

### Fase B — Adoptar `plataforma.core` donde duplica
- Identificar utilidades propias que ya existen en `plataforma/core` (version/asset,
  env_loader, web/login redirect, audit) y migrar a ellas si aplica. Conservar lo
  específico de Terreneitor. **Opcional pero recomendado** para que sea "módulo de verdad".

### Fase C — Build/runtime
- Mover `docker/Dockerfile` → `terreneitor/Dockerfile` (raíz del módulo); `COPY . /app`
  en vez de copiar solo backend/frontend; `CMD ["uvicorn","terreneitor.backend.main:app",
  "--host","0.0.0.0","--port","8005"]`; agregar `HEALTHCHECK` como los otros módulos.
- `docker-compose.yaml` (raíz): cambiar `dockerfile: docker/Dockerfile` → `Dockerfile`,
  ajustar `command`/`build`, y los volúmenes `./terreneitor/frontend` (ver Fase D).
- `backend/requirements.txt` → `terreneitor/requirements.txt`. Reconciliar `pyproject.toml`.

### Fase D — `frontend/` → `ui/`
- `git mv terreneitor/frontend terreneitor/ui`.
- Actualizar: volumen del compose (`./terreneitor/frontend:/app/frontend` → `ui`), Dockerfile
  COPY, serving en `nucleo.py`/`cerebro.py` (StaticFiles mount), y **todas** las rutas de
  assets en los HTML (`../_compartido/`, `../../shared/`, manifest, service-worker).
- Verificación navegador EXHAUSTIVA (es la fase de mayor riesgo de UI).

### Fase E — `ops/` → `scripts/` + tests/migraciones
- `ops/scripts/` → `scripts/`. Decidir destino de `ops/environments/.env` (es el `env_file`
  del compose): alinear al patrón `plataforma/ops/env/` o mantener y actualizar el compose.
- `e2e/` + `backend/tests/` → `tests/`. `backend/migrations/` → `migrations/`.

### Fase F — Limpieza final
- Borrar `backend/api`, `backend/core`, `backend/utils` si quedaron vacíos tras reubicar.
- Revisar `terreneitor/.claude/` anidado (¿cruft del repo standalone?).
- Actualizar `README.md`, `ESTADO.md`, `MIGRACION_MONSTRUO.md` al nuevo layout.

## 4. Verificación final (gate de cierre)
- `dev-rebuild.sh terreneitor` limpio.
- `curl :8005/health` OK.
- Navegador: hub + 5 módulos + login SSO, sin errores de consola, assets 200.
- `python3 plataforma/tests/ci_repo_guard.py` PASS.
- `git diff` revisado por `code-reviewer` antes de push.

## 5. Rollback
- Todo en `dev`, sin push hasta verde. Si falla: `git reset`/revert de la rama de trabajo.
- El standalone PROD (`/srv/terreneitor_dev`, repo aparte) NO se ve afectado por estos cambios.
