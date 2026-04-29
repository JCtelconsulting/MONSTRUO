# AGENTS - MONSTRUO DEV

Estas instrucciones aplican a cualquier agente ejecutado en este repositorio. Este es el único archivo de reglas operativas.
responderas corto y preciso en lenguaje natural.

## 0) Objetivo

Evitar desorden, cruces DEV/PROD y pérdida de foco en la meta de negocio (EPIC 11).

## 1) Orden de autoridad

Cuando haya conflicto, obedecer en este orden:

1. `plataforma/docs/PLAN_MAESTRO_MONSTRUO.md`
2. `plataforma/docs/PROYECTO_CONTEXTO.md`
3. `AGENTS.md` (este archivo)
4. Instrucción puntual del usuario (si no contradice 1-3)

## 2) Carga obligatoria

- Todo agente debe cargar este archivo al iniciar.
- Si no puede leerlo, debe detenerse y reportar bloqueo antes de ejecutar cambios.
- Frase de control recomendada al iniciar: `Reglas cargadas: AGENTS.md`.

## 3) Prioridad de negocio vigente

- **EPIC 11 (Ticketera) es prioridad máxima absoluta.**
- Objetivo: reemplazar la mesa externa contratada por una mesa interna profesional.
- No abrir desarrollo neto de EPIC 12+ mientras EPIC 11 no cumpla Go/No-Go definido en Plan Maestro.

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

## 6) Calidad mínima para Ticketera (EPIC 11)

- Cero errores 500 en flujos críticos: crear, asignar, responder, listar, detalle.
- Correo: hilo correcto (`In-Reply-To`/`References`) y anti-duplicado efectivo.
- Adjuntos y historial de correos operativos de punta a punta.
- Tests E2E de ticketera en verde en CI.
- UX fluida sin congelamientos ni dobles envíos.

## 7) Seguridad y Secretos

- Prohibido exponer secretos en respuestas, commits o logs.
- No subir `.env*`, credenciales o llaves al repositorio.
- No ejecutar acciones destructivas sin solicitud explícita.

## 8) Registro Documental Obligatorio

- Cambios de reglas/proceso: actualizar `plataforma/docs/PLAN_MAESTRO_MONSTRUO.md`.
- Hitos ejecutados: registrar en `plataforma/docs/PROYECTO_CONTEXTO.md`.

## 9) Git y Entrega

- Commits pequeños, mensaje claro y scope único.
- Subir a `origin/dev` salvo instrucción distinta.
- Excluir de commits: `data/`, archivos temporales, backups.

## 10) Coordinación Multi-Agente

- Antes de tocar archivos, declarar alcance para evitar colisiones.
- Si hay conflicto de cambios, priorizar integridad funcional y notificar decisión.
