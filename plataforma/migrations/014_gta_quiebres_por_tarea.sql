-- Quiebres dirigidos a un área desde una tarea concreta de un flujo.
--
-- Modelo: cuando un responsable de una tarea necesita info/acción de OTRA
-- área para poder seguir, abre un quiebre. El quiebre queda dirigido a un
-- área del flujo, BLOQUEA la tarea origen hasta resolverse, y al resolverse
-- la tarea origen retoma su estado previo (típicamente 'en_curso').
--
-- Reusamos gta.quiebres existente y la enlazamos opcionalmente a una tarea.

-- 1. Vincular quiebres a tareas (campo opcional — los quiebres viejos quedan sueltos)
ALTER TABLE gta.quiebres
    ADD COLUMN IF NOT EXISTS tarea_id INTEGER REFERENCES gta.tareas(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS tarea_estado_previo TEXT;  -- estado a restaurar al resolver

CREATE INDEX IF NOT EXISTS idx_quiebres_tarea_id ON gta.quiebres(tarea_id);

-- Lookup rápido de pendientes por área (para "mis quiebres")
CREATE INDEX IF NOT EXISTS idx_quiebres_estado_area
    ON gta.quiebres(estado, area)
    WHERE estado = 'abierto';


-- 2. Nuevo estado de tarea: esperando_quiebre
--    Cuando se abre un quiebre desde una tarea, ésta queda 'esperando_quiebre'
--    hasta que se resuelva el quiebre. NO es 'bloqueada' (eso es para deps de
--    pasos del flujo) — es un bloqueo distinto y temporal.

ALTER TABLE gta.tareas
    DROP CONSTRAINT IF EXISTS tareas_estado_check;

ALTER TABLE gta.tareas
    ADD CONSTRAINT tareas_estado_check
    CHECK (estado IN (
        'pendiente', 'en_curso', 'bloqueada',
        'cerrada', 'cancelada', 'devuelta',
        'esperando_quiebre'
    ));
