-- GTA — Restablecer FK gta.comentarios → gta.tareas tras rediseño
--
-- La migración 003 dropeó gta.tareas con CASCADE, lo que también cayó la FK
-- de gta.comentarios.tarea_id. La tabla gta.comentarios estaba vacía, así
-- que no hay datos huérfanos.

ALTER TABLE gta.comentarios
    DROP CONSTRAINT IF EXISTS comentarios_tarea_id_fkey;

ALTER TABLE gta.comentarios
    ADD CONSTRAINT comentarios_tarea_id_fkey
    FOREIGN KEY (tarea_id) REFERENCES gta.tareas(id) ON DELETE CASCADE;
