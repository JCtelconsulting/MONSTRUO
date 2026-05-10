-- Mover toda la lógica de flujos a gta.tareas (modelo único).
--
-- Antes:
--   gta.flujos       → instancia de proceso ejecutándose
--   gta.flujo_tareas → cada paso del flujo, con dependencias
--   gta.tareas       → modelo nuevo, "espejo" de flujo_tareas con FK
--
-- Ahora:
--   gta.tareas → única fuente de verdad. Las columnas nuevas guardan
--                la info que antes vivía en flujos/flujo_tareas.
--
-- Beneficio: una sola lectura para mostrar tareas, sin doble fuente que
-- se desincronice. La pestaña Tablero y la pestaña Tareas leen de aquí.

-- 1. Nuevas columnas en gta.tareas
ALTER TABLE gta.tareas
    ADD COLUMN IF NOT EXISTS flujo_id        UUID,
    ADD COLUMN IF NOT EXISTS flujo_titulo    TEXT,
    ADD COLUMN IF NOT EXISTS paso_orden      INTEGER,
    ADD COLUMN IF NOT EXISTS paso_depende_de JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS paso_bloqueante BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS datos_flujo     JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS iniciado_por_id INTEGER REFERENCES auth.users(id) ON DELETE SET NULL;

-- Índice para encontrar todas las tareas de un flujo
CREATE INDEX IF NOT EXISTS idx_tareas_flujo_id ON gta.tareas(flujo_id) WHERE flujo_id IS NOT NULL;

-- Índice para encontrar tareas bloqueadas que dependan de cierta tarea (lookup
-- por contenido del array JSON). GIN sobre paso_depende_de para resolver
-- "qué tareas tienen X en su lista de dependencias".
CREATE INDEX IF NOT EXISTS idx_tareas_paso_depende_de_gin
    ON gta.tareas USING GIN (paso_depende_de);


-- 2. Limpiar la FK vieja flujo_tarea_id antes de borrar las tablas
--    (la columna queda como historia pero ya no apunta a nada).
ALTER TABLE gta.tareas DROP CONSTRAINT IF EXISTS tareas_flujo_tarea_id_fkey;
ALTER TABLE gta.tareas DROP COLUMN IF EXISTS flujo_tarea_id;


-- 3. Eliminar tablas del sistema viejo
DROP TABLE IF EXISTS gta.flujo_eventos CASCADE;
DROP TABLE IF EXISTS gta.flujo_ayudas CASCADE;
DROP TABLE IF EXISTS gta.flujo_tareas CASCADE;
DROP TABLE IF EXISTS gta.flujos CASCADE;
