-- Ajustar el CHECK de fundacion.sede_membresias.rol para alinear con los
-- roles canónicos del organigrama vigente (sin 'ejecutiva').
--
-- Roles válidos para una membresía sede↔persona:
--   'lider_educativo'   → 1 vigente por sede (índice único parcial existente)
--   'gestora_educativa' → N por sede

ALTER TABLE fundacion.sede_membresias
    DROP CONSTRAINT IF EXISTS sede_membresias_rol_check;

ALTER TABLE fundacion.sede_membresias
    ADD CONSTRAINT sede_membresias_rol_check
    CHECK (rol IN ('lider_educativo', 'gestora_educativa'));
