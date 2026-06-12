-- Fundación — reemplaza sedes mock por las 7 sedes operativas reales (colegios).
--
-- Hasta hoy fundacion.sedes contenía 7 sedes con nombres de comunas (La Pintana,
-- Maipú, ...) que se sembraron en 007 como placeholders. Con la incorporación
-- de las planillas de matrícula y asistencia 2026 (una por colegio), pasamos al
-- modelo definitivo: una sede = un establecimiento educacional.
--
-- También agregamos las columnas `comuna` y `cupos` que vienen del diccionario
-- "Gobernanza de Datos" de la planilla.
--
-- Datos mock que se eliminan:
--   - 15 tareas de prueba en fundacion.fundacion_tareas
--   - 1 membresía de prueba en fundacion.sede_membresias
--   - 7 sedes mock (la-pintana, maipu, llay-llay, huechuraba, renca, lo-espejo,
--     cerro-navia)
--
-- TODO pendiente (no bloquea esta migración):
--   - Reemplazar el code de cada sede por el código corto oficial cuando lo
--     tengamos (visto en planilla: EBC, IPH; faltan los otros 5).
--   - Completar `cupos` para las 5 sedes que aún están en NULL.
--   - Completar `comuna` (no estaba en la planilla revisada).


-- 1) Agregar columnas nuevas
ALTER TABLE fundacion.sedes ADD COLUMN IF NOT EXISTS comuna TEXT;
ALTER TABLE fundacion.sedes ADD COLUMN IF NOT EXISTS cupos  INTEGER;


-- 2) Borrar datos mock (en orden por FKs)
DELETE FROM fundacion.fundacion_tareas;
DELETE FROM fundacion.sede_membresias;
DELETE FROM fundacion.sedes;

-- Reiniciar contador de IDs para que las sedes reales empiecen en 1
ALTER SEQUENCE fundacion.sedes_id_seq RESTART WITH 1;


-- 3) Sembrar las 7 sedes operativas reales
INSERT INTO fundacion.sedes (code, nombre, region, cupos, orden) VALUES
    ('el-buen-camino',            'Sede El Buen Camino',          'Región Metropolitana', 60,   10),
    ('liceo-francisco-mery',      'Liceo Francisco Mery',         NULL,                   NULL, 20),
    ('instituto-padre-hurtado',   'Instituto Padre Hurtado',      NULL,                   30,   30),
    ('escuela-basica-las-palmas', 'Escuela Básica Las Palmas',    NULL,                   NULL, 40),
    ('escuela-domingo-santa-maria','Escuela Domingo Santa María', NULL,                   NULL, 50),
    ('colegio-san-sebastian',     'Colegio San Sebastián',        NULL,                   NULL, 60),
    ('colegio-cree',              'Colegio CREE',                 NULL,                   NULL, 70);
