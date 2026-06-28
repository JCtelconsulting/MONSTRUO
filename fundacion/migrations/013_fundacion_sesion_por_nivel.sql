-- Fundación — sesion_dia ahora se identifica por (sede + nivel + fecha).
--
-- Como las sesiones que existían no tenían nivel asignado y eran datos de
-- prueba muy escasos (apenas creados desde la UI nueva), las dejamos en NULL
-- inicialmente. Sin embargo, para nuevas sesiones, nivel_id será obligatorio.
--
-- La UNIQUE constraint vieja era (sede_id, fecha). La cambiamos por
-- (sede_id, nivel_id, fecha) — permite 3 sesiones por sede por día (una por
-- nivel atendido).

-- 1) Agregar columna nivel_id
ALTER TABLE fundacion.sesion_dia
    ADD COLUMN IF NOT EXISTS nivel_id INTEGER
        REFERENCES fundacion.niveles(id) ON DELETE RESTRICT;

-- 2) Migrar sesiones existentes (si hay): asignar el nivel "prekinder_kinder"
--    como default solo para no perderlas. Las sesiones reales se crearán con
--    nivel desde la app.
UPDATE fundacion.sesion_dia
   SET nivel_id = (SELECT id FROM fundacion.niveles WHERE codigo = 'prekinder_kinder')
 WHERE nivel_id IS NULL;

-- 3) Reemplazar el UNIQUE (sede_id, fecha) por uno que incluya nivel.
--    Lo hacemos con un índice único parcial sobre nivel_id NOT NULL: así
--    funciona como UNIQUE compuesto cuando hay nivel.
ALTER TABLE fundacion.sesion_dia
    DROP CONSTRAINT IF EXISTS sesion_dia_sede_id_fecha_key;

ALTER TABLE fundacion.sesion_dia
    ALTER COLUMN nivel_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sesion_dia_sede_nivel_fecha
    ON fundacion.sesion_dia (sede_id, nivel_id, fecha);

CREATE INDEX IF NOT EXISTS idx_sesion_dia_nivel
    ON fundacion.sesion_dia (nivel_id);
