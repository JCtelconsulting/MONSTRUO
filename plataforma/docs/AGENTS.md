# AGENTS - MONSTRUO DEV

Estas instrucciones aplican a cualquier agente ejecutado en este repositorio. Este es el único archivo de reglas operativas.

Ubicación canónica: `plataforma/docs/AGENTS.md`. Claude Code entra vía `CLAUDE.md` en la raíz, que apunta a este archivo. Otros agentes (Codex, etc.) deben leerlo directo desde aquí.

Responder corto y preciso en lenguaje natural.

## 0) Objetivo

Evitar desorden, cruces DEV/PROD y pérdida de foco en la meta de negocio (EPIC 11).

## 1) Orden de autoridad

Cuando haya conflicto, obedecer en este orden:

1. `plataforma/docs/plan/GUIA_MAESTRA.md`
2. `plataforma/docs/PROYECTO_CONTEXTO.md`
3. `plataforma/docs/AGENTS.md` (este archivo)
4. Instrucción puntual del usuario (si no contradice 1-3)

## 2) Carga obligatoria

- Todo agente debe cargar `plataforma/docs/AGENTS.md` al iniciar.
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
3. **VERIFICACIÓN** con evidencia (PASS/FAIL)
4. **CIERRE** con resumen técnico

Reglas:

- Una tarea a la vez.
- No meter extras fuera de scope antes de cerrar la tarea solicitada.

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

- Cambios de reglas/proceso: actualizar `plataforma/docs/plan/GUIA_MAESTRA.md`.
- Hitos ejecutados: registrar en `plataforma/docs/PROYECTO_CONTEXTO.md`.
- Cambios de UI/estilos: respetar `plataforma/docs/estandares/DESIGN_SYSTEM.md`.

## 9) Git y Entrega

- Commits pequeños, mensaje claro y scope único.
- Subir a `origin/dev` salvo instrucción distinta.
- Excluir de commits: `data/`, archivos temporales, backups.

## 10) Coordinación Multi-Agente

- Antes de tocar archivos, declarar alcance para evitar colisiones.
- Si hay conflicto de cambios, priorizar integridad funcional y notificar decisión.
