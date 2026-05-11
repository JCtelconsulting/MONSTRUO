-- gta.avisos_revision — avisos para tareas cerradas cuando hubo cambios
-- en pasos anteriores del flujo después de su cierre.
--
-- Cuándo se generan: cuando alguien cierra un paso que fue reabierto por
-- una devolución (desde un paso posterior), y al cerrar modificó
-- datos_flujo o tocó adjuntos. En ese caso, los pasos cerrados intermedios
-- entre el paso modificado y el paso que devolvió reciben un aviso.
--
-- Quién lo ve: el responsable del paso afectado en la pestaña Tareas
-- (banner amarillo sobre la tarea). Puede marcar como revisado si
-- considera que el cambio no le afecta, o devolver al paso modificado
-- si necesita rehacer su trabajo.

CREATE TABLE IF NOT EXISTS gta.avisos_revision (
    id              SERIAL PRIMARY KEY,
    tarea_id        INTEGER NOT NULL REFERENCES gta.tareas(id) ON DELETE CASCADE,
    flujo_id        UUID NOT NULL,
    por_tarea_id    INTEGER REFERENCES gta.tareas(id) ON DELETE SET NULL,
    motivo          TEXT,  -- "modificó datos_flujo", "agregó adjunto X", etc.
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revisado_at     TIMESTAMP,
    revisado_por    INTEGER REFERENCES auth.users(id) ON DELETE SET NULL
);

-- Lookup principal: ¿esta tarea tiene avisos pendientes?
CREATE INDEX IF NOT EXISTS idx_avisos_tarea_pendientes
    ON gta.avisos_revision(tarea_id)
    WHERE revisado_at IS NULL;

-- Para mostrar todos los avisos del flujo
CREATE INDEX IF NOT EXISTS idx_avisos_flujo ON gta.avisos_revision(flujo_id);
