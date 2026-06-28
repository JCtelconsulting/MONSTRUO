-- Fundación — sedes y membresías persona ↔ sede (versionadas)
--
-- Replica el patrón de gta.area_membresias: el scope se vincula a la sede,
-- no al rol del usuario. Esto permite que una persona pase entre sedes sin
-- crear roles nuevos por cada combinación.
--
-- Reglas:
--   - Una sede puede tener N gestoras_educativas, N ejecutivas y como mucho
--     UN líder educativo vigente.
--   - Una persona puede estar en N sedes (caso típico: admins lo están en
--     todas; pero los admins NO necesitan membresía: el helper SQL los
--     considera con scope total).
--   - Roles de membresía: 'lider_educativo' | 'gestora_educativa' | 'ejecutiva'.

CREATE TABLE IF NOT EXISTS fundacion.sedes (
    id              SERIAL PRIMARY KEY,
    code            TEXT UNIQUE NOT NULL,
    nombre          TEXT NOT NULL,
    region          TEXT,
    descripcion     TEXT,
    icono           TEXT,
    color           TEXT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    orden           INTEGER NOT NULL DEFAULT 99,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed inicial — 7 sedes que hoy están hardcodeadas en fundacion.js.
INSERT INTO fundacion.sedes (code, nombre, region, descripcion, icono, color, orden) VALUES
    ('la-pintana',   'La Pintana',   'Región Metropolitana',   'Seguimiento operativo de talleres y compromisos comunitarios.', 'fa-school',          '#4facfe', 10),
    ('maipu',        'Maipú',        'Región Metropolitana',   'Planificación académica y coordinación de actividades semanales.', 'fa-chalkboard-user', '#61d1a7', 20),
    ('llay-llay',    'Llay-Llay',    'Región de Valparaíso',   'Cobertura territorial, agenda de terreno y soporte formativo.', 'fa-route',           '#9f7aea', 30),
    ('huechuraba',   'Huechuraba',   'Región Metropolitana',   'Control de reportes, planificación y apoyo transversal.', 'fa-building',        '#f59e0b', 40),
    ('renca',        'Renca',        'Región Metropolitana',   'Gestión de stock crítico y reposición de insumos clave.', 'fa-boxes-stacked',   '#14b8a6', 50),
    ('lo-espejo',    'Lo Espejo',    'Región Metropolitana',   'Ejecución de calendario de clases y hitos de comunidad.', 'fa-calendar-check',  '#ef5da8', 60),
    ('cerro-navia',  'Cerro Navia',  'Región Metropolitana',   'Soporte de terreno, monitoreo de tareas y continuidad operativa.', 'fa-people-group',   '#60a5fa', 70)
ON CONFLICT (code) DO NOTHING;


-- Membresías persona ↔ sede ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fundacion.sede_membresias (
    id              SERIAL PRIMARY KEY,
    usuario_id      INTEGER NOT NULL REFERENCES fundacion.users(id) ON DELETE CASCADE,
    sede_id         INTEGER NOT NULL REFERENCES fundacion.sedes(id) ON DELETE CASCADE,
    rol             TEXT NOT NULL CHECK (rol IN ('lider_educativo', 'gestora_educativa', 'ejecutiva')),
    desde           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hasta           TIMESTAMP,
    asignado_por    INTEGER REFERENCES fundacion.users(id) ON DELETE SET NULL,
    motivo          TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 1 líder educativo vigente por sede
CREATE UNIQUE INDEX IF NOT EXISTS uq_sedemem_lider_vigente
    ON fundacion.sede_membresias (sede_id)
    WHERE rol = 'lider_educativo' AND hasta IS NULL;

-- No duplicar (usuario, sede, rol) vigente
CREATE UNIQUE INDEX IF NOT EXISTS uq_sedemem_user_sede_rol_vigente
    ON fundacion.sede_membresias (usuario_id, sede_id, rol)
    WHERE hasta IS NULL;

CREATE INDEX IF NOT EXISTS idx_sedemem_sede_vigente
    ON fundacion.sede_membresias (sede_id)
    WHERE hasta IS NULL;

CREATE INDEX IF NOT EXISTS idx_sedemem_usuario_vigente
    ON fundacion.sede_membresias (usuario_id)
    WHERE hasta IS NULL;


-- Helpers SQL ───────────────────────────────────────────────────────────

-- ¿El usuario es admin (Monstruo o Fundación) o jefatura de Fundación?
-- Esos perfiles tienen scope total a sedes sin necesidad de membresía.
CREATE OR REPLACE FUNCTION fundacion.es_super_scope(p_usuario_id INTEGER)
RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM fundacion.users
        WHERE id = p_usuario_id
          AND COALESCE(role,'') IN (
              'admin', 'directora_social', 'jefa_pedagogica', 'coordinadora_territorial'
          )
    );
$$ LANGUAGE SQL STABLE;

-- IDs de sedes accesibles por un usuario.
-- - Si tiene super scope, devuelve TODAS las sedes activas.
-- - Si no, devuelve solo las que tiene asignadas en sede_membresias vigente.
CREATE OR REPLACE FUNCTION fundacion.sedes_accesibles(p_usuario_id INTEGER)
RETURNS TABLE (sede_id INTEGER) AS $$
    SELECT s.id
    FROM fundacion.sedes s
    WHERE s.activo = TRUE
      AND (
          fundacion.es_super_scope(p_usuario_id)
          OR EXISTS (
              SELECT 1 FROM fundacion.sede_membresias m
              WHERE m.usuario_id = p_usuario_id
                AND m.sede_id = s.id
                AND m.hasta IS NULL
          )
      )
    ORDER BY s.orden, s.code;
$$ LANGUAGE SQL STABLE;

-- ¿Tiene acceso a una sede específica?
CREATE OR REPLACE FUNCTION fundacion.tiene_acceso_sede(p_usuario_id INTEGER, p_sede_id INTEGER)
RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM fundacion.sedes_accesibles(p_usuario_id) WHERE sede_id = p_sede_id
    );
$$ LANGUAGE SQL STABLE;

-- Líder educativo vigente de una sede (NULL si no hay)
CREATE OR REPLACE FUNCTION fundacion.lider_vigente_sede(p_sede_id INTEGER)
RETURNS INTEGER AS $$
    SELECT usuario_id
    FROM fundacion.sede_membresias
    WHERE sede_id = p_sede_id
      AND rol = 'lider_educativo'
      AND hasta IS NULL
    LIMIT 1;
$$ LANGUAGE SQL STABLE;
