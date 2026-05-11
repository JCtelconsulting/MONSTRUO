-- Fundación — registro de sesiones pedagógicas.
--
-- Cada día de operación una gestora registra qué se hizo. Una "sesión" es
-- (sede, fecha). Dentro de una sesión hay N bloques en orden (Juegos para
-- Crecer, Taller Socioemocional, Colación, etc.).
--
-- El clima del día completo se guarda a nivel sesion_dia (no por bloque),
-- siguiendo la sugerencia de la encargada en el correo original.

-- ── Sesión del día por sede ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fundacion.sesion_dia (
    id                      SERIAL PRIMARY KEY,
    sede_id                 INTEGER NOT NULL REFERENCES fundacion.sedes(id) ON DELETE CASCADE,
    fecha                   DATE NOT NULL,
    -- Clima general del día
    clima_opcion_id         INTEGER REFERENCES fundacion.clima_opciones(id),
    situaciones_relevantes  TEXT,
    estrategias_aplicadas   TEXT,
    notas                   TEXT,
    -- Trazabilidad
    creado_por              INTEGER REFERENCES auth.users(id) ON DELETE SET NULL,
    creado_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_por         INTEGER REFERENCES auth.users(id) ON DELETE SET NULL,
    actualizado_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cerrado                 BOOLEAN NOT NULL DEFAULT FALSE,
                            -- cuando cerrado=TRUE, ya no se puede editar
    UNIQUE (sede_id, fecha)
);

CREATE INDEX IF NOT EXISTS idx_sesion_dia_sede_fecha ON fundacion.sesion_dia(sede_id, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_sesion_dia_fecha ON fundacion.sesion_dia(fecha DESC);


-- ── Bloques que componen una sesión ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fundacion.sesion_bloque (
    id                      SERIAL PRIMARY KEY,
    sesion_dia_id           INTEGER NOT NULL REFERENCES fundacion.sesion_dia(id) ON DELETE CASCADE,
    orden                   INTEGER NOT NULL,
    -- Qué tipo de bloque
    bloque_tipo_id          INTEGER NOT NULL REFERENCES fundacion.bloque_tipos(id),
    bloque_subtipo_id       INTEGER REFERENCES fundacion.bloque_subtipos(id),
    -- Contenido pedagógico
    nombre_actividad        TEXT,
    resultado_aprendizaje   TEXT,
    hora_inicio             TIME,
    hora_fin                TIME,
    -- Ejecución real
    se_ejecuto              BOOLEAN NOT NULL DEFAULT TRUE,
    motivo_no_ejecucion     TEXT,
    -- Adaptaciones realizadas (reporte d del correo)
    adaptacion              TEXT,
    notas                   TEXT,
    creado_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (sesion_dia_id, orden)
);

CREATE INDEX IF NOT EXISTS idx_sesion_bloque_sesion ON fundacion.sesion_bloque(sesion_dia_id);
CREATE INDEX IF NOT EXISTS idx_sesion_bloque_tipo ON fundacion.sesion_bloque(bloque_tipo_id);


-- ── Competencias trabajadas en cada bloque (N×M) ────────────────────────────
CREATE TABLE IF NOT EXISTS fundacion.sesion_bloque_competencias (
    id                  SERIAL PRIMARY KEY,
    sesion_bloque_id    INTEGER NOT NULL REFERENCES fundacion.sesion_bloque(id) ON DELETE CASCADE,
    competencia_id      INTEGER NOT NULL REFERENCES fundacion.competencias(id),
    UNIQUE (sesion_bloque_id, competencia_id)
);

CREATE INDEX IF NOT EXISTS idx_sbc_bloque ON fundacion.sesion_bloque_competencias(sesion_bloque_id);
CREATE INDEX IF NOT EXISTS idx_sbc_comp ON fundacion.sesion_bloque_competencias(competencia_id);


-- ── Materiales usados en cada bloque ────────────────────────────────────────
-- product_id (FK a bodega.products) si la gestora elige del catálogo. Si no,
-- nombre_libre como texto. Cantidades opcionales.
CREATE TABLE IF NOT EXISTS fundacion.sesion_bloque_materiales (
    id                      SERIAL PRIMARY KEY,
    sesion_bloque_id        INTEGER NOT NULL REFERENCES fundacion.sesion_bloque(id) ON DELETE CASCADE,
    product_id              INTEGER REFERENCES bodega.products(id) ON DELETE SET NULL,
    nombre_libre            TEXT,
    cantidad_solicitada     NUMERIC(10,2),
    cantidad_usada          NUMERIC(10,2),
    notas                   TEXT,
    -- Al menos uno: producto del catálogo o nombre libre
    CHECK (product_id IS NOT NULL OR (nombre_libre IS NOT NULL AND length(trim(nombre_libre)) > 0))
);

CREATE INDEX IF NOT EXISTS idx_sbm_bloque ON fundacion.sesion_bloque_materiales(sesion_bloque_id);
CREATE INDEX IF NOT EXISTS idx_sbm_producto ON fundacion.sesion_bloque_materiales(product_id)
    WHERE product_id IS NOT NULL;
