-- Fundación — catálogo de niveles educativos.
--
-- Cada sede atiende a niños/as de los 3 niveles a la vez, pero cada grupo
-- (nivel) hace SU propia actividad. La planificación oficial está por nivel,
-- no por sede entera. Por eso introducimos este catálogo y luego ligamos
-- sesion_dia y planificacion_anual a (sede + nivel + fecha).

CREATE TABLE IF NOT EXISTS fundacion.niveles (
    id              SERIAL PRIMARY KEY,
    codigo          TEXT UNIQUE NOT NULL,
    nombre          TEXT NOT NULL,
    descripcion     TEXT,
    color           TEXT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    orden           INTEGER NOT NULL DEFAULT 99
);

INSERT INTO fundacion.niveles (codigo, nombre, descripcion, color, orden) VALUES
    ('prekinder_kinder', 'Prekinder y Kinder',  'Educación Inicial',                      '#4facfe', 10),
    ('1ro_2do',          '1° y 2° básico',      'Primer ciclo de básica (NB1)',           '#61d1a7', 20),
    ('3ro_4to',          '3° y 4° básico',      'Primer ciclo de básica (NB2)',           '#f59e0b', 30)
ON CONFLICT (codigo) DO NOTHING;
