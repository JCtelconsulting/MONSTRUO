-- Orden custom de áreas para que las columnas del diagrama de procesos
-- queden en un orden que tenga sentido para el negocio:
--   comercial → pmo → preventa → redes → bodega → proveedores → finanzas
-- ... y después las áreas administrativas.
--
-- El campo `orden` también lo usa el resto de la app (selectores, listas
-- de áreas), así que este orden se aplica globalmente, no solo al diagrama.

UPDATE gta.areas SET orden = 10  WHERE code = 'comercial';
UPDATE gta.areas SET orden = 20  WHERE code = 'pmo';
UPDATE gta.areas SET orden = 30  WHERE code = 'preventa';
UPDATE gta.areas SET orden = 40  WHERE code = 'redes';
UPDATE gta.areas SET orden = 50  WHERE code = 'bodega';
UPDATE gta.areas SET orden = 60  WHERE code = 'proveedores';
UPDATE gta.areas SET orden = 70  WHERE code = 'finanzas';
UPDATE gta.areas SET orden = 80  WHERE code = 'sistemas';
UPDATE gta.areas SET orden = 90  WHERE code = 'capital_humano';
UPDATE gta.areas SET orden = 100 WHERE code = 'prevencion_riesgos';
UPDATE gta.areas SET orden = 110 WHERE code = 'contabilidad';
