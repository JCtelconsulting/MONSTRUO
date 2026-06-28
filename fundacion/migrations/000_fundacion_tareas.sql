-- Fundación — tabla de tareas (calendario de actividades por sede/curso).
--
-- Separación fase 3: antes esta tabla se creaba inline en el init_db monolítico
-- de Monstruo. Al recortar init_db, pasa a ser una migración propia de Fundación.
-- Es la primera (000) porque la 004 (sedes reales) limpia datos de prueba de aquí.

CREATE TABLE IF NOT EXISTS fundacion.fundacion_tareas (
    id              SERIAL PRIMARY KEY,
    titulo          TEXT NOT NULL,
    descripcion     TEXT,
    fecha_inicio    TIMESTAMP NOT NULL,
    fecha_fin       TIMESTAMP,
    asignado_a      TEXT,                       -- username del ejecutivo
    creado_by       TEXT,
    sede            TEXT,
    estado          TEXT DEFAULT 'pendiente',   -- pendiente, en_progreso, completado, cancelado
    color           TEXT DEFAULT '#4facfe',     -- visualización en calendario
    reporte         TEXT,                       -- feedback de la gestora
    imprevistos     TEXT,
    reportado_at    TIMESTAMP,
    curso           TEXT,
    categoria       TEXT,
    categoria_madre TEXT,
    subcategoria    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fundacion_tareas_asignado ON fundacion.fundacion_tareas(asignado_a);
CREATE INDEX IF NOT EXISTS idx_fundacion_tareas_fecha    ON fundacion.fundacion_tareas(fecha_inicio);
CREATE INDEX IF NOT EXISTS idx_fundacion_tareas_sede     ON fundacion.fundacion_tareas(sede);
CREATE INDEX IF NOT EXISTS idx_fundacion_tareas_curso    ON fundacion.fundacion_tareas(curso);
