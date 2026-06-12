-- Limpieza del subsistema deprecated "quiebres por tarea".
--
-- Cuando se hizo el refactor de devolución unificada (commit 640057c) se
-- eliminó el código que usaba esto, pero se dejó el schema por
-- compatibilidad. Ahora que el modelo nuevo está validado y nadie usa más
-- estos campos, los sacamos.
--
-- Cambios:
-- 1. Si quedó alguna tarea en estado 'esperando_quiebre' (no debería),
--    la pasamos a 'pendiente' antes de tocar el CHECK.
-- 2. Sacamos 'esperando_quiebre' del CHECK de gta.tareas.estado.
-- 3. Quitamos las columnas tarea_id y tarea_estado_previo de gta.quiebres
--    junto con sus índices (estaban para vincular un quiebre con la tarea
--    que lo originó — el modelo nuevo no usa quiebres por tarea, los
--    quiebres genéricos del sistema viejo siguen funcionando sin esto).

-- 1. Defensivo: nada debería estar 'esperando_quiebre', pero por si acaso
UPDATE gta.tareas
SET estado = 'pendiente',
    updated_at = CURRENT_TIMESTAMP
WHERE estado = 'esperando_quiebre';

-- 2. Reescribir CHECK sin 'esperando_quiebre'
ALTER TABLE gta.tareas
    DROP CONSTRAINT IF EXISTS tareas_estado_check;

ALTER TABLE gta.tareas
    ADD CONSTRAINT tareas_estado_check
    CHECK (estado IN (
        'pendiente', 'en_curso', 'bloqueada',
        'cerrada', 'cancelada', 'devuelta'
    ));

-- 3. Limpiar columnas y índices muertos en gta.quiebres
DROP INDEX IF EXISTS gta.idx_quiebres_tarea_id;
DROP INDEX IF EXISTS gta.idx_quiebres_estado_area;

ALTER TABLE gta.quiebres
    DROP COLUMN IF EXISTS tarea_id,
    DROP COLUMN IF EXISTS tarea_estado_previo;
