-- Fundación — catálogos pedagógicos.
--
-- Contenido extraído de los documentos de planificación 2026 que viven en
-- fundacion/data/planificaciones/. Si la encargada actualiza el catálogo de
-- competencias o agrega un nuevo tipo de bloque, se modifica esta migración
-- (o se hace un INSERT desde la app — los catálogos son editables en runtime
-- para que un admin no necesite migración para agregar opciones nuevas).

-- ── Dominios SEL (familias de competencias) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS fundacion.competencia_dominios (
    id              SERIAL PRIMARY KEY,
    codigo          TEXT UNIQUE NOT NULL,
    nombre          TEXT NOT NULL,
    color           TEXT,
    orden           INTEGER NOT NULL DEFAULT 99
);

INSERT INTO fundacion.competencia_dominios (codigo, nombre, color, orden) VALUES
    ('AC', 'Autoconciencia',            '#4facfe', 10),
    ('AG', 'Autogestión',               '#61d1a7', 20),
    ('CS', 'Conciencia Social',         '#f59e0b', 30),
    ('HR', 'Habilidades Relacionales',  '#9f7aea', 40),
    ('RD', 'Responsabilidad Decisional','#ef5da8', 50)
ON CONFLICT (codigo) DO NOTHING;


-- ── Catálogo de 37 competencias ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fundacion.competencias (
    id              SERIAL PRIMARY KEY,
    codigo          TEXT UNIQUE NOT NULL,                   -- AC1, AG3, etc.
    dominio_id      INTEGER NOT NULL REFERENCES fundacion.competencia_dominios(id),
    descripcion     TEXT NOT NULL,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    orden           INTEGER NOT NULL DEFAULT 99
);

CREATE INDEX IF NOT EXISTS idx_competencias_dominio ON fundacion.competencias(dominio_id);

INSERT INTO fundacion.competencias (codigo, dominio_id, descripcion, orden) VALUES
    ('AC1', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AC'), 'Observa, describe y valora sus características personales, habilidades, intereses e historia.', 1),
    ('AC2', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AC'), 'Identifica las propias emociones.', 2),
    ('AC3', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AC'), 'Demuestra honestidad e integridad.', 3),
    ('AC4', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AC'), 'Relaciona sentimientos, valores y pensamientos.', 4),
    ('AC5', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AC'), 'Examina los prejuicios y los sesgos.', 5),
    ('AC6', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AC'), 'Experimenta la autoeficacia (confianza en la propia capacidad para lograr los resultados pretendidos).', 6),
    ('AC7', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AC'), 'Tiene una mentalidad de crecimiento.', 7),
    ('AC8', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AC'), 'Desarrolla intereses y un sentido de propósito.', 8),

    ('AG1', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AG'), 'Gestiona las propias emociones.', 1),
    ('AG2', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AG'), 'Identifica y utiliza estrategias de gestión del estrés.', 2),
    ('AG3', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AG'), 'Demuestra autodisciplina y automotivación.', 3),
    ('AG4', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AG'), 'Establece objetivos personales y colectivos.', 4),
    ('AG5', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AG'), 'Planifica objetivos y tareas.', 5),
    ('AG6', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AG'), 'Utiliza habilidades de planificación y organización (placeholder — confirmar texto oficial con la fundación).', 6),
    ('AG7', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='AG'), 'Demuestra capacidad de acción personal y colectiva.', 7),

    ('CS1', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='CS'), 'Reconoce el punto de vista de los demás.', 1),
    ('CS2', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='CS'), 'Reconoce los puntos fuertes de los demás.', 2),
    ('CS3', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='CS'), 'Demuestra empatía y compasión.', 3),
    ('CS4', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='CS'), 'Demuestra preocupación por los sentimientos de los demás.', 4),
    ('CS5', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='CS'), 'Expresa la gratitud.', 5),
    ('CS6', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='CS'), 'Identifica diversas normas sociales, incluidas las injustas.', 6),
    ('CS7', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='CS'), 'Reconoce las exigencias y oportunidades de la situación.', 7),
    ('CS8', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='CS'), 'Reconoce, describe y valora sus grupos de pertenencia (familia, curso, pares).', 8),

    ('HR1', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='HR'), 'Se comunica de manera efectiva.', 1),
    ('HR2', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='HR'), 'Se relaciona con otros de manera positiva.', 2),
    ('HR3', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='HR'), 'Participa en equipos y colabora en la resolución conjunta de problemas.', 3),
    ('HR4', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='HR'), 'Resuelve conflictos de forma constructiva.', 4),
    ('HR5', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='HR'), 'Demuestra liderazgo cuando participa en actividades grupales.', 5),
    ('HR6', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='HR'), 'Busca u ofrece apoyo o ayuda cuando se necesita.', 6),
    ('HR7', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='HR'), 'Defiende los derechos de los demás.', 7),

    ('RD1', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='RD'), 'Demuestra curiosidad y apertura mental.', 1),
    ('RD2', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='RD'), 'Identifica soluciones para problemas personales y sociales.', 2),
    ('RD3', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='RD'), 'Aprende a emitir un juicio razonado.', 3),
    ('RD4', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='RD'), 'Analiza información, datos y hechos.', 4),
    ('RD5', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='RD'), 'Anticipa y evalúa las consecuencias de las propias acciones.', 5),
    ('RD6', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='RD'), 'Reconoce la utilidad de las habilidades de pensamiento crítico tanto dentro como fuera de la escuela.', 6),
    ('RD7', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='RD'), 'Reflexiona sobre el propio papel para promover el bienestar personal.', 7),
    ('RD8', (SELECT id FROM fundacion.competencia_dominios WHERE codigo='RD'), 'Evalúa el impacto personal, interpersonal, comunitario e institucional.', 8)
ON CONFLICT (codigo) DO NOTHING;


-- ── Tipos de bloque (lo que pasa en cada momento del día) ───────────────────
CREATE TABLE IF NOT EXISTS fundacion.bloque_tipos (
    id              SERIAL PRIMARY KEY,
    codigo          TEXT UNIQUE NOT NULL,
    nombre          TEXT NOT NULL,
    descripcion     TEXT,
    -- Si requiere subtipo (ej. juegos_para_crecer → psicomotor/sensorial/...)
    requiere_subtipo BOOLEAN NOT NULL DEFAULT FALSE,
    -- Si en este bloque se trabajan competencias SEL (taller, viernes_comunidad)
    permite_competencias BOOLEAN NOT NULL DEFAULT FALSE,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    orden           INTEGER NOT NULL DEFAULT 99,
    color           TEXT,
    icono           TEXT
);

INSERT INTO fundacion.bloque_tipos (codigo, nombre, descripcion, requiere_subtipo, permite_competencias, orden, color, icono) VALUES
    ('juegos_para_crecer',  'Juegos para Crecer',  'Juegos por dimensión (psicomotor, sensorial, cognitivo, afectivo, artístico, adaptativo).', TRUE,  FALSE, 10, '#4facfe', 'fa-dice'),
    ('taller_socioemocional','Taller Socioemocional','Bloque principal donde se trabajan las competencias SEL del catálogo.',                      FALSE, TRUE,  20, '#9f7aea', 'fa-heart'),
    ('glifing',             'Glifing Grupal',      'Lectura comprensiva grupal.',                                                                  FALSE, FALSE, 30, '#61d1a7', 'fa-book-open-reader'),
    ('colacion',            'Colación',            'Tiempo de alimentación compartida.',                                                           FALSE, FALSE, 40, '#f59e0b', 'fa-apple-whole'),
    ('juego_libre',         'Juego Libre',         'Tiempo de juego sin estructura, social.',                                                      FALSE, FALSE, 50, '#14b8a6', 'fa-children'),
    ('viernes_comunidad',   'Viernes de Comunidad','Actividad especial semanal de la fundación.',                                                  FALSE, TRUE,  60, '#ef5da8', 'fa-people-group'),
    ('pichintun',           'Pichintún',           'Bloque específico de educación inicial (mesas de juegos, puzzles, títeres).',                  FALSE, FALSE, 70, '#60a5fa', 'fa-puzzle-piece')
ON CONFLICT (codigo) DO NOTHING;


-- ── Subtipos de Juegos para Crecer ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fundacion.bloque_subtipos (
    id              SERIAL PRIMARY KEY,
    bloque_tipo_id  INTEGER NOT NULL REFERENCES fundacion.bloque_tipos(id) ON DELETE CASCADE,
    codigo          TEXT NOT NULL,
    nombre          TEXT NOT NULL,
    descripcion     TEXT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    orden           INTEGER NOT NULL DEFAULT 99,
    UNIQUE (bloque_tipo_id, codigo)
);

INSERT INTO fundacion.bloque_subtipos (bloque_tipo_id, codigo, nombre, orden) VALUES
    ((SELECT id FROM fundacion.bloque_tipos WHERE codigo='juegos_para_crecer'), 'psicomotor', 'Psicomotor', 10),
    ((SELECT id FROM fundacion.bloque_tipos WHERE codigo='juegos_para_crecer'), 'sensorial',  'Sensorial',  20),
    ((SELECT id FROM fundacion.bloque_tipos WHERE codigo='juegos_para_crecer'), 'cognitivo',  'Cognitivo',  30),
    ((SELECT id FROM fundacion.bloque_tipos WHERE codigo='juegos_para_crecer'), 'afectivo',   'Afectivo',   40),
    ((SELECT id FROM fundacion.bloque_tipos WHERE codigo='juegos_para_crecer'), 'artistico',  'Artístico',  50),
    ((SELECT id FROM fundacion.bloque_tipos WHERE codigo='juegos_para_crecer'), 'adaptativo', 'Adaptativo', 60)
ON CONFLICT (bloque_tipo_id, codigo) DO NOTHING;


-- ── Opciones de clima/convivencia del día ───────────────────────────────────
CREATE TABLE IF NOT EXISTS fundacion.clima_opciones (
    id          SERIAL PRIMARY KEY,
    codigo      TEXT UNIQUE NOT NULL,
    nombre      TEXT NOT NULL,
    descripcion TEXT,
    color       TEXT,
    icono       TEXT,
    activo      BOOLEAN NOT NULL DEFAULT TRUE,
    orden       INTEGER NOT NULL DEFAULT 99
);

-- Propuesta inicial — la encargada de Fundación puede ajustar/agregar desde la app.
INSERT INTO fundacion.clima_opciones (codigo, nombre, descripcion, color, icono, orden) VALUES
    ('excelente',   'Excelente',   'Clima óptimo, niños y niñas motivados y conectados.',           '#10b981', 'fa-face-laugh-beam',  10),
    ('bueno',       'Bueno',       'Clima positivo en general.',                                    '#22c55e', 'fa-face-smile',       20),
    ('regular',     'Regular',     'Hubo momentos de dispersión o desinterés, pero se sostuvo.',    '#f59e0b', 'fa-face-meh',         30),
    ('agitado',     'Agitado',     'Grupo muy disperso o inquieto, costó sostener la atención.',    '#f97316', 'fa-face-tired',       40),
    ('conflictivo', 'Conflictivo', 'Hubo conflictos relevantes entre niños o disrupciones serias.', '#ef4444', 'fa-face-angry',       50)
ON CONFLICT (codigo) DO NOTHING;
