-- Fundación — catálogo de actividades pedagógicas.
--
-- Las ~3.300 actividades únicas de los docx oficiales viven acá. Sirven como:
-- 1) Autocomplete cuando la gestora escribe el nombre de la actividad en un
--    bloque de sesión.
-- 2) Fuente de las competencias y materiales típicos de cada actividad.
--
-- Identidad: (nombre + bloque_tipo + bloque_subtipo). Una misma "Pelota de la
-- amistad" para Taller Socioemocional es la misma actividad en cualquier nivel.
-- Las instrucciones detalladas por nivel van en planificacion_anual_bloque.

CREATE TABLE IF NOT EXISTS fundacion.actividades (
    id                      SERIAL PRIMARY KEY,
    nombre                  TEXT NOT NULL,
    nombre_normalizado      TEXT NOT NULL,
                            -- lowercase sin acentos para búsqueda fuzzy
    bloque_tipo_id          INTEGER NOT NULL REFERENCES fundacion.bloque_tipos(id),
    bloque_subtipo_id       INTEGER REFERENCES fundacion.bloque_subtipos(id),
    resultado_aprendizaje   TEXT,
    materiales_tipicos      TEXT,            -- texto libre extraído del docx
    fuente_doc              TEXT,            -- 'Prekinder-Kinder', '1ro-2do (1er sem)', etc.
    veces_referenciada      INTEGER NOT NULL DEFAULT 0,
    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_actividad_nombre_tipo_subtipo
    ON fundacion.actividades (nombre_normalizado, bloque_tipo_id,
                              COALESCE(bloque_subtipo_id, -1));

CREATE INDEX IF NOT EXISTS idx_actividades_tipo
    ON fundacion.actividades (bloque_tipo_id);

-- Búsqueda por trigramas para autocomplete tolerante a typos (opcional).
-- Se intenta crear; si pg_trgm no está disponible, se ignora.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
EXCEPTION WHEN OTHERS THEN
    -- Si no se puede instalar la extensión (permisos), se ignora.
    NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_actividades_nombre_trgm
    ON fundacion.actividades USING gin (nombre_normalizado gin_trgm_ops);


-- Relación N×M: competencias asociadas a cada actividad.
CREATE TABLE IF NOT EXISTS fundacion.actividad_competencias (
    id              SERIAL PRIMARY KEY,
    actividad_id    INTEGER NOT NULL REFERENCES fundacion.actividades(id) ON DELETE CASCADE,
    competencia_id  INTEGER NOT NULL REFERENCES fundacion.competencias(id),
    UNIQUE (actividad_id, competencia_id)
);

CREATE INDEX IF NOT EXISTS idx_actcomp_actividad
    ON fundacion.actividad_competencias (actividad_id);
CREATE INDEX IF NOT EXISTS idx_actcomp_competencia
    ON fundacion.actividad_competencias (competencia_id);


-- Conexión opcional desde sesion_bloque al catálogo: si la gestora elige una
-- actividad del catálogo, lo dejamos enlazado. Si escribió texto libre, queda
-- NULL. Esto permite reportes que agrupen por "actividad oficial vs improvisada".
ALTER TABLE fundacion.sesion_bloque
    ADD COLUMN IF NOT EXISTS actividad_id INTEGER
        REFERENCES fundacion.actividades(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_sesion_bloque_actividad
    ON fundacion.sesion_bloque (actividad_id)
    WHERE actividad_id IS NOT NULL;
