-- Fundación — asociar cada sede con su planilla de Google Drive.
--
-- Cada sede tiene UNA planilla en Drive con matrícula y asistencia 2026.
-- Guardamos el ID acá (no en código) para que un admin pueda cambiar la
-- planilla desde la app si en 2027 se rotan los archivos.

ALTER TABLE fundacion.sedes
    ADD COLUMN IF NOT EXISTS drive_spreadsheet_id TEXT;

-- Sembrar IDs actuales (planillas 2026)
UPDATE fundacion.sedes SET drive_spreadsheet_id = '1sA3yEpAu5_fVg3bIZYSbHv7guuTbznlFSNYudhfZPQo'
    WHERE code = 'el-buen-camino';
UPDATE fundacion.sedes SET drive_spreadsheet_id = '1okpSIakUDKgWHX5MFw5Aes5-n56x0WqUdReSxZVp27w'
    WHERE code = 'liceo-francisco-mery';
UPDATE fundacion.sedes SET drive_spreadsheet_id = '1YDHRPL2d5SJJyUy8p-cwpTl23x4I7F_6t8k0lUqAfBA'
    WHERE code = 'instituto-padre-hurtado';
UPDATE fundacion.sedes SET drive_spreadsheet_id = '17-_t1iDZnGw4gg1BzwaFncwK9Y5HluoOnES7_fOGVWE'
    WHERE code = 'escuela-basica-las-palmas';
UPDATE fundacion.sedes SET drive_spreadsheet_id = '1qMIpBx_m_QmdrKTaFGlSMMZyLIM3MMPDKDf8Ln58DEA'
    WHERE code = 'escuela-domingo-santa-maria';
UPDATE fundacion.sedes SET drive_spreadsheet_id = '1DHOjqURXt0fvPVx7Vu0dfVMTcnETeFFXNJMfD7qkXUc'
    WHERE code = 'colegio-san-sebastian';
UPDATE fundacion.sedes SET drive_spreadsheet_id = '1Xa5eYNf2mXtWT0JRYKih9c1ijxSZabryWi5HxZe2AAo'
    WHERE code = 'colegio-cree';

CREATE UNIQUE INDEX IF NOT EXISTS uq_sedes_drive_spreadsheet_id
    ON fundacion.sedes (drive_spreadsheet_id)
    WHERE drive_spreadsheet_id IS NOT NULL;
