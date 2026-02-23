# AGENTS - MONSTRUO DEV

Estas instrucciones aplican a cualquier agente ejecutado en este repositorio.

## Regla de carga obligatoria
- Cargar y obedecer: `.agents/rules/reglas-monstruo-dev.md`.
- Si no se puede leer ese archivo, detener ejecucion y reportar bloqueo.

## Orden de autoridad
1. `docs/PLAN_MAESTRO_MONSTRUO.md`
2. `docs/PROYECTO_CONTEXTO.md`
3. `.agents/rules/reglas-monstruo-dev.md`
4. Instruccion puntual del usuario (si no contradice 1-3)

## Prioridad de negocio
- EPIC 11 (Ticketera) es prioridad maxima hasta cierre Go/No-Go profesional.
- No abrir desarrollo neto de EPIC 12+ salvo incidentes criticos o bloqueo tecnico.

## Entornos
- Rama por defecto de trabajo: `dev`.
- Prohibido desplegar a `main/prod` sin aprobacion explicita del usuario.
- Respetar separacion DEV/PROD (env files, credenciales, jobs, URLs).

## Registro obligatorio
- Cambios de reglas/proceso: actualizar `docs/PLAN_MAESTRO_MONSTRUO.md`.
- Hitos ejecutados: registrar en `docs/PROYECTO_CONTEXTO.md`.
