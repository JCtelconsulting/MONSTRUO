---
trigger: always_on
---

# MONSTRUO DEV REGLAS (v2026-02-14)

## 0) Objetivo
Este archivo es la regla operativa canonica para agentes en `/srv/monstruo_dev`.
Su fin es evitar desorden, cruces DEV/PROD y perdida de foco en la meta de negocio.

## 1) Orden de autoridad (anti-conflicto)
Cuando haya conflicto, obedecer en este orden:
1. `docs/PLAN_MAESTRO_MONSTRUO.md`
2. `docs/PROYECTO_CONTEXTO.md`
3. `.agent/rules/monstruo-dev-reglas.md` (este archivo)
4. Instruccion puntual del usuario (si no contradice 1-3)

## 2) Carga obligatoria
- Todo agente debe cargar este archivo al iniciar.
- Si no puede leerlo, debe detenerse y reportar bloqueo antes de ejecutar cambios.
- Frase de control recomendada al iniciar: `Reglas cargadas: monstruo-dev-reglas.md`.

## 3) Prioridad de negocio vigente
- EPIC 11 (Ticketera) es prioridad maxima absoluta.
- Objetivo: reemplazar la mesa externa contratada por una mesa interna profesional.
- No abrir desarrollo neto de EPIC 12+ mientras EPIC 11 no cumpla Go/No-Go definido en Plan Maestro.

## 4) Separacion DEV/PROD (no negociable)
- Rama de trabajo base: `dev` (salvo instruccion explicita del usuario).
- Prohibido desplegar a `main/prod` sin autorizacion explicita.
- Nombres canonicos de entorno:
  - PROD: `project=monstruo`, `stack=monstruo`, `env_file=/srv/monstruo/.env.server`
  - DEV: `project=monstruo_dev`, `stack=monstruo-dev`, `env_file=/srv/monstruo_dev/.env.server.dev`
- Prohibido mezclar credenciales, URLs o jobs entre DEV y PROD.

## 5) Flujo de trabajo obligatorio
Cada tarea debe cerrar este ciclo:
1. PLAN breve
2. EJECUCION acotada
3. VERIFICACION con evidencia (PASS/FAIL)
4. CIERRE con resumen tecnico

Reglas:
- Una tarea a la vez.
- No meter extras fuera de scope antes de cerrar la tarea solicitada.
- Si aparece un bloqueo, detener y reportar causa real + opcion de correccion.

## 6) Calidad minima para Ticketera (EPIC 11)
- Cero errores 500 en flujos criticos: crear, asignar, responder, listar, detalle.
- Correo: hilo correcto (`In-Reply-To`/`References`) y anti-duplicado efectivo.
- Adjuntos y historial de correos operativos de punta a punta.
- Tests E2E de ticketera en verde en CI para flujos definidos en plan.
- UX fluida sin congelamientos ni dobles envios por reintento.

## 7) Seguridad y secretos
- Prohibido exponer secretos en respuestas, commits o logs.
- No subir `.env*`, credenciales, llaves o tokens.
- No ejecutar acciones destructivas sin solicitud explicita del usuario.

## 8) Registro documental obligatorio
- Si se toma una decision de arquitectura/proceso, registrar en:
  - `docs/PLAN_MAESTRO_MONSTRUO.md` (regla/politica permanente)
  - `docs/PROYECTO_CONTEXTO.md` (hito operativo con fecha y estado)

## 9) Git y entrega
- Commits pequenos, mensaje claro y scope unico.
- Subir a `origin/dev` salvo instruccion distinta del usuario.
- Excluir de commits: `data/`, archivos temporales, backups sueltos, secretos.

## 10) Coordinacion multi-agente
- Antes de tocar archivos, declarar alcance para evitar colision.
- Si otro agente ya modifico algo, revisar diff y trabajar encima sin revertir su trabajo.
- Si hay conflicto de cambios, priorizar integridad funcional y notificar decision.
