-- Fundación — planificación anual oficial.
--
-- Es la plantilla pedagógica del año, por (nivel, fecha). Cada día tiene N
-- bloques planificados con actividad sugerida, hora, etc. Las gestoras la
-- usan como guía: al abrir un día en la UI, ven "lo que tocaba según el plan
-- oficial" y pueden cargarlo como punto de partida de la sesión ejecutada.
--
-- Importante: la planificación es **referencia**. Las sesiones reales viven
-- en sesion_dia / sesion_bloque y son lo que la gestora reporta.

CREATE TABLE IF NOT EXISTS fundacion.planificacion_dia (
    id                  SERIAL PRIMARY KEY,
    nivel_id            INTEGER NOT NULL REFERENCES fundacion.niveles(id) ON DELETE CASCADE,
    fecha               DATE NOT NULL,
    numero_dia          INTEGER,            -- "DÍA 1, DÍA 2..." según docx
    dia_semana          TEXT,               -- LUNES, MARTES, ... (informativo)
    fuente_doc          TEXT,               -- de qué archivo viene
    notas               TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (nivel_id, fecha)
);

CREATE INDEX IF NOT EXISTS idx_planif_dia_fecha
    ON fundacion.planificacion_dia (fecha);
CREATE INDEX IF NOT EXISTS idx_planif_dia_nivel_fecha
    ON fundacion.planificacion_dia (nivel_id, fecha);


CREATE TABLE IF NOT EXISTS fundacion.planificacion_bloque (
    id                      SERIAL PRIMARY KEY,
    planificacion_dia_id    INTEGER NOT NULL REFERENCES fundacion.planificacion_dia(id) ON DELETE CASCADE,
    orden                   INTEGER NOT NULL,
    bloque_tipo_id          INTEGER NOT NULL REFERENCES fundacion.bloque_tipos(id),
    bloque_subtipo_id       INTEGER REFERENCES fundacion.bloque_subtipos(id),
    actividad_id            INTEGER REFERENCES fundacion.actividades(id) ON DELETE SET NULL,
    nombre_actividad        TEXT,           -- redundante con actividad.nombre pero útil si no se enlazó
    resultado_aprendizaje   TEXT,
    hora_inicio             TIME,
    hora_fin                TIME,
    instruccion             TEXT,           -- contenido pedagógico extraído del docx
    materiales_sugeridos    TEXT,
    notas                   TEXT,
    UNIQUE (planificacion_dia_id, orden)
);

CREATE INDEX IF NOT EXISTS idx_planif_bloque_dia
    ON fundacion.planificacion_bloque (planificacion_dia_id);
CREATE INDEX IF NOT EXISTS idx_planif_bloque_actividad
    ON fundacion.planificacion_bloque (actividad_id);


-- Competencias planificadas para cada bloque (N×M).
CREATE TABLE IF NOT EXISTS fundacion.planificacion_bloque_competencias (
    id                          SERIAL PRIMARY KEY,
    planificacion_bloque_id     INTEGER NOT NULL REFERENCES fundacion.planificacion_bloque(id) ON DELETE CASCADE,
    competencia_id              INTEGER NOT NULL REFERENCES fundacion.competencias(id),
    UNIQUE (planificacion_bloque_id, competencia_id)
);

CREATE INDEX IF NOT EXISTS idx_planif_bloque_comp_bloque
    ON fundacion.planificacion_bloque_competencias (planificacion_bloque_id);
CREATE INDEX IF NOT EXISTS idx_planif_bloque_comp_comp
    ON fundacion.planificacion_bloque_competencias (competencia_id);
