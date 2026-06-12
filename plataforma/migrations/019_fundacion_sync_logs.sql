-- Fundación — log de corridas del sync con Google Drive.
--
-- Una fila por cada vez que se ejecuta el sync (ya sea por cron o manual).
-- Si una corrida toca varias sedes, hay una fila padre con sede_id=NULL y
-- N filas hijas (una por sede). El padre se identifica por run_id.

CREATE TABLE IF NOT EXISTS fundacion.sync_logs (
    id                          SERIAL PRIMARY KEY,
    run_id                      UUID NOT NULL,                  -- agrupa la corrida global
    sede_id                     INTEGER REFERENCES fundacion.sedes(id) ON DELETE SET NULL,
    -- NULL en la fila padre, con sede en las filas hijas
    started_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at                 TIMESTAMP,
    status                      TEXT NOT NULL DEFAULT 'running',
                                -- 'running' | 'ok' | 'error' | 'partial'
    trigger                     TEXT NOT NULL,
                                -- 'cron' | 'manual' | 'api'
    actor                       TEXT,                           -- usuario que disparó (si manual)
    alumnos_creados             INTEGER NOT NULL DEFAULT 0,
    alumnos_actualizados        INTEGER NOT NULL DEFAULT 0,
    alumnos_desaparecidos       INTEGER NOT NULL DEFAULT 0,     -- estaban en DB pero ya no en planilla
    asistencias_insertadas      INTEGER NOT NULL DEFAULT 0,
    asistencias_actualizadas    INTEGER NOT NULL DEFAULT 0,
    codigos_desconocidos        INTEGER NOT NULL DEFAULT 0,     -- celdas con código fuera del diccionario
    mensaje                     TEXT,
    detalles                    JSONB,                          -- libre, para drill-down
    CHECK (status IN ('running', 'ok', 'error', 'partial')),
    CHECK (trigger IN ('cron', 'manual', 'api'))
);

CREATE INDEX IF NOT EXISTS idx_sync_logs_run ON fundacion.sync_logs (run_id);
CREATE INDEX IF NOT EXISTS idx_sync_logs_sede_started ON fundacion.sync_logs (sede_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_logs_started ON fundacion.sync_logs (started_at DESC);
