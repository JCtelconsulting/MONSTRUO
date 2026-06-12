-- gta.flujo_eventos — log cronológico de qué pasó en cada flujo.
--
-- Para el tablero: timeline visual del flujo (quién hizo qué y cuándo).
-- Cada acción significativa registra una entrada acá: inicio del flujo,
-- cierre de tarea, devolución, reporte/resolución de quiebre.
--
-- NO reemplaza otros logs (auditoría, comentarios libres, etc.). Es una
-- vista cronológica simplificada para visualización rápida.

-- Si quedó la tabla del modelo viejo (flujo_id INTEGER), la dropeamos
-- y recreamos limpia (no tiene datos útiles porque los flujos viejos
-- se eliminaron en migración 011).
DROP TABLE IF EXISTS gta.flujo_eventos CASCADE;

CREATE TABLE gta.flujo_eventos (
    id          SERIAL PRIMARY KEY,
    flujo_id    UUID NOT NULL,
    tarea_id    INTEGER REFERENCES gta.tareas(id) ON DELETE SET NULL,
    tipo        TEXT NOT NULL,    -- ver constantes en services/flujo_eventos.py
    mensaje     TEXT,             -- texto humano-readable, opcional
    actor       TEXT,             -- username del que disparó la acción
    metadata    JSONB DEFAULT '{}'::jsonb,  -- detalles según tipo
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Lookup principal: timeline ordenado por flujo
CREATE INDEX IF NOT EXISTS idx_flujo_eventos_flujo_created
    ON gta.flujo_eventos(flujo_id, created_at);

-- Lookup secundario: eventos por tarea
CREATE INDEX IF NOT EXISTS idx_flujo_eventos_tarea
    ON gta.flujo_eventos(tarea_id) WHERE tarea_id IS NOT NULL;
