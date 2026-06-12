-- gta.tareas.estado — agregar 'devuelta' al set permitido.
--
-- Nuevo estado para pasos de validación (tipo: "validacion" en pasos_definicion):
-- cuando el validador rechaza, su tarea queda en 'devuelta' y la tarea destino
-- (típicamente el paso predecesor que cargó los datos) se reabre a 'pendiente'.
--
-- Estados:
--   - 'pendiente'  → asignada, esperando que alguien la tome
--   - 'en_curso'   → alguien la tomó como responsable
--   - 'bloqueada'  → espera que se cierre alguna dependencia
--   - 'cerrada'    → terminada OK
--   - 'cancelada'  → terminada sin éxito (no aplica, no se hizo)
--   - 'devuelta'   → validador rechazó; el paso destino se reabrió para corregir

ALTER TABLE gta.tareas
    DROP CONSTRAINT IF EXISTS tareas_estado_check;

ALTER TABLE gta.tareas
    ADD CONSTRAINT tareas_estado_check
    CHECK (estado IN ('pendiente', 'en_curso', 'bloqueada', 'cerrada', 'cancelada', 'devuelta'));
