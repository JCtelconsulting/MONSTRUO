-- Fundación — alumnos y asistencia diaria.
--
-- Datos sincronizados desde las planillas de cada sede (hoja Matriculas y hoja
-- Asistencia). La app es solo de lectura sobre estos datos: la planilla manda
-- y el sync sobrescribe lo que esté en la DB.
--
-- Reglas de identidad:
--   - rut_normalizado = rut sin puntos, sin guión, sin espacios, en lowercase.
--     Se calcula en el sync (no en SQL) para no agregar lógica de stored proc.
--   - Un alumno está identificado por (sede_id, rut_normalizado).
--   - Si una persona aparece en 2 sedes, son 2 filas distintas (caso raro).

CREATE TABLE IF NOT EXISTS fundacion.alumnos (
    id                          SERIAL PRIMARY KEY,
    sede_id                     INTEGER NOT NULL REFERENCES fundacion.sedes(id) ON DELETE CASCADE,
    correlativo                 INTEGER,                -- col 2 "N°" en planilla
    -- Identificación
    nombre_completo             TEXT NOT NULL,
    rut                         TEXT,                   -- como viene en planilla
    rut_normalizado             TEXT,                   -- limpio para joins
    fecha_nacimiento            DATE,
    edad                        INTEGER,
    nacionalidad                TEXT,
    tiene_nee                   BOOLEAN,                -- "Si"/"No" en planilla
    nee_detalle                 TEXT,
    sexo                        TEXT,                   -- Hombre / Mujer
    -- Académico
    curso_colegio               TEXT,                   -- "3ro", "Kinder", etc.
    curso_after                 TEXT,                   -- "Prekinder - Kinder"
    plan                        TEXT,                   -- "Full" / "Flexible"
    dias_flex_por_semana        INTEGER,
    gestora_a_cargo             TEXT,                   -- nombre, texto libre
    anos_en_after               TEXT,                   -- "1er año", "2do año"
    estado_alumno               TEXT,                   -- "Activo"/"Inactivo" (fórmula)
    -- Cuidador
    cuidador_nombre             TEXT,
    cuidador_rut                TEXT,
    cuidador_fecha_nacimiento   DATE,
    cuidador_edad               INTEGER,
    cuidador_nacionalidad       TEXT,
    cuidador_sexo               TEXT,
    cuidador_telefono           TEXT,
    grupo_familiar              INTEGER,
    -- Estado matrícula / proceso
    estado_matricula            TEXT,                   -- "Completado", "Cancelada", etc.
    fecha_matriculacion         TEXT,                   -- la planilla a veces guarda "2026", no fecha completa
    reunion_informativa         BOOLEAN,
    formulario_postulacion      BOOLEAN,
    entrevista_psicosocial      TEXT,                   -- "Realizada" / otros
    documentos_firmados         BOOLEAN,
    fecha_inicio_participacion  DATE,
    fecha_inicio_adaptacion     DATE,
    evaluacion_adaptacion       TEXT,                   -- fecha o texto
    asistencia_regular          BOOLEAN,                -- "SI"/"NO"
    riesgo_desercion            BOOLEAN,                -- "SI"/"NO"
    fecha_desercion             DATE,
    motivo_desercion            TEXT,
    -- Variables auxiliares (fórmulas calculadas en la planilla)
    ano_ingreso_after           INTEGER,
    mes_ingreso_after           INTEGER,
    mes_matricula               INTEGER,
    mes_desercion               INTEGER,
    matricula_activa            BOOLEAN,                -- 1/0 en planilla
    -- Metadata sync
    synced_at                   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Soft "delete" cuando un alumno desaparece de la planilla
    presente_en_planilla        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_alumnos_sede_rut
    ON fundacion.alumnos (sede_id, rut_normalizado)
    WHERE rut_normalizado IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_alumnos_sede ON fundacion.alumnos (sede_id);
CREATE INDEX IF NOT EXISTS idx_alumnos_matricula_activa ON fundacion.alumnos (sede_id, matricula_activa);


-- Asistencia diaria: una fila por (alumno, fecha) con el código de la planilla.
CREATE TABLE IF NOT EXISTS fundacion.asistencia_diaria (
    id              SERIAL PRIMARY KEY,
    alumno_id       INTEGER NOT NULL REFERENCES fundacion.alumnos(id) ON DELETE CASCADE,
    sede_id         INTEGER NOT NULL REFERENCES fundacion.sedes(id) ON DELETE CASCADE,
    fecha           DATE NOT NULL,
    codigo          TEXT NOT NULL,                  -- 'P' | 'A' | 'AJ' | 'F/V' | 'ST' | 'NM' | 'FLEX' | otro
    codigo_conocido BOOLEAN NOT NULL DEFAULT TRUE,  -- false si llegó un valor fuera del diccionario
    synced_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_asistencia_alumno_fecha
    ON fundacion.asistencia_diaria (alumno_id, fecha);

CREATE INDEX IF NOT EXISTS idx_asistencia_sede_fecha
    ON fundacion.asistencia_diaria (sede_id, fecha);

CREATE INDEX IF NOT EXISTS idx_asistencia_codigo_desconocido
    ON fundacion.asistencia_diaria (sede_id, fecha)
    WHERE codigo_conocido = FALSE;
