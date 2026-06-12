-- gta.procesos.estado — CHECK constraint con los 3 valores válidos.
--
-- Hoy la columna es TEXT sin restricción y acepta cualquier string. Cerramos
-- el set a:
--   - 'borrador'  → en construcción, no se puede iniciar flujo, no aparece en listados de catálogo
--   - 'activo'    → publicado, listo para usar
--   - 'archivado' → ya no se usa, queda como histórico
--
-- Defensivo: si hay filas con valores fuera de la lista, las normalizamos
-- a 'activo' antes de aplicar el constraint.

UPDATE gta.procesos
SET estado = 'activo'
WHERE estado IS NULL OR estado NOT IN ('borrador', 'activo', 'archivado');

ALTER TABLE gta.procesos
    DROP CONSTRAINT IF EXISTS procesos_estado_check;

ALTER TABLE gta.procesos
    ADD CONSTRAINT procesos_estado_check
    CHECK (estado IN ('borrador', 'activo', 'archivado'));
