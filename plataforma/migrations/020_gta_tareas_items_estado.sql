-- Sub-items (checklist) dentro de un paso del proceso.
--
-- Modelo: en pasos_definicion cada paso puede tener un array opcional
-- `items` con sub-tareas:
--   {
--     "id": "equipos_redes",
--     "titulo": "Equipos de red verificados",
--     "requerido_para_cerrar": true,
--     "desbloquea_pasos": [10]
--   }
-- Esto se setea desde el editor de procesos y vive en la plantilla (TEXT).
--
-- En tiempo de ejecución, cada gta.tareas guarda el estado de tickeo en
-- esta nueva columna JSONB items_estado:
--   {
--     "equipos_redes": { "tickeado": true, "tickeado_por_id": 25, "tickeado_at": "..." },
--     "materiales":    { "tickeado": false }
--   }
--
-- Comportamiento:
-- - Al cerrar la tarea: si algún item con requerido_para_cerrar=true no está
--   tickeado, se rechaza el cierre.
-- - Al tickear un item con desbloquea_pasos: esos pasos del flujo, si están
--   bloqueada, pasan a pendiente (desbloqueo directo, sin esperar al cierre
--   del paso completo).

ALTER TABLE gta.tareas
    ADD COLUMN IF NOT EXISTS items_estado JSONB DEFAULT '{}'::jsonb;
