-- GTA — Membresías persona ↔ subárea (versionadas)
--
-- Modelo: una tarea pertenece a una subárea, no a una persona. La membresía
-- de una persona en una subárea es un atributo versionado (desde/hasta) para
-- que cambios de personal no rompan flujos ni historial.
--
-- Reglas:
--   - Una persona tiene UNA membresía principal vigente a la vez (es_principal=true).
--   - Una subárea tiene como mucho UN líder vigente.
--   - Se cierra una membresía seteando hasta=now(); se "abre" otra con desde=now().
--
-- No se hace backfill automático: las áreas/subáreas existentes con
-- lider_username quedan como referencia histórica (ver gta.areas / gta.subareas).
-- Los líderes/miembros se cargan desde la UI cuando esté lista.

CREATE TABLE IF NOT EXISTS gta.area_membresias (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    subarea_id      INTEGER NOT NULL REFERENCES gta.subareas(id) ON DELETE CASCADE,
    rol             TEXT NOT NULL CHECK (rol IN ('miembro', 'lider')),
    es_principal    BOOLEAN NOT NULL DEFAULT FALSE,
    desde           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hasta           TIMESTAMP,
    asignado_por    INTEGER REFERENCES auth.users(id) ON DELETE SET NULL,
    motivo          TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 1 membresía vigente principal por usuario
CREATE UNIQUE INDEX IF NOT EXISTS uq_membresia_principal_vigente
    ON gta.area_membresias (usuario_id)
    WHERE es_principal = TRUE AND hasta IS NULL;

-- 1 líder vigente por subárea
CREATE UNIQUE INDEX IF NOT EXISTS uq_membresia_lider_vigente
    ON gta.area_membresias (subarea_id)
    WHERE rol = 'lider' AND hasta IS NULL;

-- 1 membresía vigente por (usuario, subárea) — no duplicar
CREATE UNIQUE INDEX IF NOT EXISTS uq_membresia_user_subarea_vigente
    ON gta.area_membresias (usuario_id, subarea_id)
    WHERE hasta IS NULL;

CREATE INDEX IF NOT EXISTS idx_membresia_subarea_vigente
    ON gta.area_membresias (subarea_id)
    WHERE hasta IS NULL;

CREATE INDEX IF NOT EXISTS idx_membresia_usuario_vigente
    ON gta.area_membresias (usuario_id)
    WHERE hasta IS NULL;


-- Helpers SQL ───────────────────────────────────────────────────────────
-- Líder vigente de una subárea (NULL si no hay)
CREATE OR REPLACE FUNCTION gta.lider_vigente(p_subarea_id INTEGER)
RETURNS INTEGER AS $$
    SELECT usuario_id
    FROM gta.area_membresias
    WHERE subarea_id = p_subarea_id
      AND rol = 'lider'
      AND hasta IS NULL
    LIMIT 1;
$$ LANGUAGE SQL STABLE;

-- IDs de miembros vigentes de una subárea (líderes incluidos)
CREATE OR REPLACE FUNCTION gta.miembros_vigentes(p_subarea_id INTEGER)
RETURNS TABLE (usuario_id INTEGER, rol TEXT, es_principal BOOLEAN) AS $$
    SELECT m.usuario_id, m.rol, m.es_principal
    FROM gta.area_membresias m
    WHERE m.subarea_id = p_subarea_id
      AND m.hasta IS NULL
    ORDER BY (m.rol = 'lider') DESC, m.es_principal DESC, m.desde;
$$ LANGUAGE SQL STABLE;

-- Subáreas vigentes de un usuario
CREATE OR REPLACE FUNCTION gta.subareas_de_usuario(p_usuario_id INTEGER)
RETURNS TABLE (subarea_id INTEGER, rol TEXT, es_principal BOOLEAN) AS $$
    SELECT m.subarea_id, m.rol, m.es_principal
    FROM gta.area_membresias m
    WHERE m.usuario_id = p_usuario_id
      AND m.hasta IS NULL
    ORDER BY m.es_principal DESC, m.desde;
$$ LANGUAGE SQL STABLE;
