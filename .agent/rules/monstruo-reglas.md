---
trigger: always_on
---

# MONSTRUO REGLAS (PUENTE / DEPRECADO)

Este archivo se mantiene solo por compatibilidad con agentes antiguos.

## Regla obligatoria
- Las reglas canonicas vigentes estan en:
  - `.agent/rules/monstruo-dev-reglas.md`
- Si hay conflicto entre ambos archivos, **gana `monstruo-dev-reglas.md`**.
- Todo agente debe cargar y obedecer `monstruo-dev-reglas.md` antes de ejecutar cambios.

## Motivo
- Alineacion al contexto actual (CI/CD por rama, separacion DEV/PROD, prioridad maxima EPIC 11 Ticketera).
