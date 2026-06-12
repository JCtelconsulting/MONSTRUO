# AGENTS - MONSTRUO DEV

Estas instrucciones aplican a cualquier agente ejecutado en este repositorio. Este es el único archivo de reglas operativas.

Ubicación canónica: `AGENTS.md` en la raíz del repo. Claude Code lo carga vía `CLAUDE.md` (puntero corto). Otros agentes (Codex, Cursor, Aider, Gemini) lo leen directo siguiendo la convención multi-agente.

Responder corto y preciso en lenguaje natural.

## 0) Objetivo

Evitar desorden, cruces DEV/PROD y pérdida de foco en la meta de negocio (EPIC 11).

## 1) Orden de autoridad

Cuando haya conflicto, obedecer en este orden:

1. `plataforma/docs/GUIA_MAESTRA.md`
2. `plataforma/docs/PROYECTO_CONTEXTO.md`
3. `AGENTS.md` (este archivo, raíz del repo)
4. Instrucción puntual del usuario (si no contradice 1-3)

## 2) Carga obligatoria

- Todo agente debe cargar `AGENTS.md` (raíz) al iniciar.
- Claude Code lo carga indirectamente vía `CLAUDE.md` en la raíz (puntero).
- Si no puede leerlo, debe detenerse y reportar bloqueo antes de ejecutar cambios.
- Frase de control recomendada al iniciar: `Reglas cargadas: AGENTS.md`.

## 3) Prioridad de negocio vigente

- **GTA (Gestión y Tableros por Área) es la prioridad actual.**
- Ticketera (EPIC 11) ya está en producción y entra en mantención post-PROD; no se abre trabajo en ticketera salvo bug crítico.
- No mezclar trabajo de GTA con trabajo de otras apps en el mismo commit/PR.

## 4) Separación DEV/PROD (No Negociable)

- Rama de trabajo base: `dev` (salvo instrucción explícita del usuario).
- Prohibido desplegar a `main/prod` sin autorización explícita.
- Nombres canónicos de entorno:
  - **PROD:** `project=monstruo`, `stack=monstruo`, env: `/srv/monstruo/plataforma/ops/env/.env.server`
  - **DEV:** `project=monstruo_dev`, `stack=monstruo-dev`, env: `/srv/monstruo_dev/plataforma/ops/env/.env.server.dev`
- Prohibido mezclar credenciales, URLs o jobs entre DEV y PROD.

## 5) Flujo de Trabajo Obligatorio

Cada tarea debe cerrar este ciclo:

1. **PLAN** breve
2. **EJECUCIÓN** acotada
3. **VERIFICACIÓN** con evidencia (PASS/FAIL) — incluye rebuild de containers afectados (ver §5.1)
4. **CIERRE** con resumen técnico

Reglas:

- Una tarea a la vez.
- No meter extras fuera de scope antes de cerrar la tarea solicitada.

### 5.1) Rebuild obligatorio tras cambios de código

**Antes de declarar un cambio listo o pedirle al usuario que lo verifique**, siempre rebuildear los containers afectados. Aplica a cualquier cambio en código: UI (HTML/CSS/JS), backend (Python), Dockerfile, etc.

```bash
ASSET_VERSION=$(git rev-parse --short HEAD) \
  APP_UID=$(id -u) APP_GID=$(id -g) \
  docker compose --env-file plataforma/ops/env/.env.server.dev up -d --build <containers>
```

Luego validar runtime con `curl` al endpoint relevante (`/health`, GET del recurso modificado) y comparar contra el contenido esperado.

**Por qué importa:** sin rebuild, `window.ASSET_VERSION` queda con el SHA anterior, el navegador sigue sirviendo HTML cacheado mientras el JS es nuevo, y se producen mismatches silenciosos (el JS busca IDs que ya no existen en el HTML cacheado). Síntoma típico: el usuario reporta "no veo los cambios" o "no pasa nada al apretar".

Hacerlo **antes** del commit es preferible: detecta errores de sintaxis o imports rotos antes de pushear, y deja la evidencia PASS/FAIL en VERIFICACIÓN.

## 6) Calidad mínima por app

- Cero errores 500 en flujos críticos.
- Tests automáticos en verde en CI antes de mergear a `dev`.
- UX fluida sin congelamientos ni dobles envíos.
- Cualquier cambio de schema acompañado de migración en `app/migrations/`.

Apps en mantención (no se abre trabajo nuevo salvo bug crítico):

- ticketera (EPIC 11 cerrado, en producción).

## 7) Seguridad y Secretos

- Prohibido exponer secretos en respuestas, commits o logs.
- No subir `.env*`, credenciales o llaves al repositorio.
- No ejecutar acciones destructivas sin solicitud explícita.

## 8) Registro Documental Obligatorio

- Cambios de reglas/proceso: actualizar `plataforma/docs/GUIA_MAESTRA.md`.
- Hitos ejecutados: registrar en `plataforma/docs/PROYECTO_CONTEXTO.md`.
- Cambios de UI/estilos: respetar `plataforma/docs/estandares/DESIGN_SYSTEM.md`.

## 9) Git y Entrega

- Commits pequeños, mensaje claro y scope único.
- Subir a `origin/dev` salvo instrucción distinta.
- Excluir de commits: `data/`, archivos temporales, backups.

## 10) Coordinación Multi-Agente

- Antes de tocar archivos, declarar alcance para evitar colisiones.
- Si hay conflicto de cambios, priorizar integridad funcional y notificar decisión.
