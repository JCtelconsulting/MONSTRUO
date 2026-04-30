-- GTA — Migración inicial
-- Crea el schema y las tablas base del módulo.
-- Runner: plataforma/core/migrations.py (pendiente)

CREATE SCHEMA IF NOT EXISTS gta;

CREATE TABLE IF NOT EXISTS gta.procesos (
    id                SERIAL PRIMARY KEY,
    nombre            TEXT NOT NULL,
    area              TEXT NOT NULL,
    descripcion       TEXT,
    sla_horas         INTEGER,
    icono             TEXT DEFAULT 'fa-tasks',
    pasos_definicion  TEXT DEFAULT '[]',   -- JSON: ["paso 1", "paso 2"]
    campos_formulario TEXT DEFAULT '[]',   -- JSON: [{"key":"x","label":"X","type":"text"}]
    estado            TEXT DEFAULT 'activo',
    creado_por        TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gta.solicitudes (
    id               SERIAL PRIMARY KEY,
    proceso_id       INTEGER REFERENCES gta.procesos(id) ON DELETE SET NULL,
    titulo           TEXT NOT NULL,
    descripcion      TEXT,
    area             TEXT NOT NULL,
    prioridad        TEXT DEFAULT 'media',
    estado           TEXT DEFAULT 'pendiente',
    creado_por       TEXT,
    asignado_a       TEXT,
    pasos_estado     TEXT DEFAULT '[]',    -- JSON: [{"completado":false,"bloqueado":false}]
    campos_extra     TEXT DEFAULT '{}',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gta.comentarios (
    id         SERIAL PRIMARY KEY,
    tarea_id   INTEGER REFERENCES gta.solicitudes(id) ON DELETE CASCADE,
    autor      TEXT NOT NULL,
    texto      TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gta.quiebres (
    id             SERIAL PRIMARY KEY,
    descripcion    TEXT NOT NULL,
    area           TEXT NOT NULL,
    tipo           TEXT DEFAULT 'sin_proceso',
    solicitud_id   INTEGER REFERENCES gta.solicitudes(id) ON DELETE SET NULL,
    reportado_por  TEXT,
    estado         TEXT DEFAULT 'abierto',
    nota_resolucion TEXT,
    resuelto_por   TEXT,
    resuelto_at    TIMESTAMP,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_gta_solicitudes_estado   ON gta.solicitudes(estado);
CREATE INDEX IF NOT EXISTS idx_gta_solicitudes_area     ON gta.solicitudes(area);
CREATE INDEX IF NOT EXISTS idx_gta_solicitudes_creado   ON gta.solicitudes(creado_por);
CREATE INDEX IF NOT EXISTS idx_gta_quiebres_estado      ON gta.quiebres(estado);
CREATE INDEX IF NOT EXISTS idx_gta_comentarios_tarea    ON gta.comentarios(tarea_id);
