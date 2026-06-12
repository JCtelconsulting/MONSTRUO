-- Renombre canónico de roles según organigrama Fundación
--   monitora        → gestora_educativa  (Gestora Educativa)
--   encargado_sede  → lider_educativo    (Líder Educativo)
-- Ejecutiva, admin, directora_social, jefa_pedagogica, coordinadora_territorial
-- quedan como roles sin cambios (los 3 últimos quedan disponibles para usar pero
-- a fines de permisos siguen siendo equivalentes a 'admin').

-- Roles primarios
UPDATE auth.users SET role = 'gestora_educativa'
  WHERE role = 'monitora';

UPDATE auth.users SET role = 'lider_educativo'
  WHERE role = 'encargado_sede';

-- secondary_roles es JSON-en-texto. Reemplazamos los strings exactos
-- (envueltos en comillas dobles para evitar matches parciales).
UPDATE auth.users
SET secondary_roles = REPLACE(
        REPLACE(
            COALESCE(secondary_roles, '[]'),
            '"monitora"', '"gestora_educativa"'
        ),
        '"encargado_sede"', '"lider_educativo"'
    )
WHERE secondary_roles LIKE '%"monitora"%' OR secondary_roles LIKE '%"encargado_sede"%';

-- Renombrar permisos por rol en core.sys_role_permissions (si existe la tabla)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='core' AND table_name='sys_role_permissions'
    ) THEN
        UPDATE core.sys_role_permissions SET role = 'gestora_educativa'
          WHERE role = 'monitora';
        UPDATE core.sys_role_permissions SET role = 'lider_educativo'
          WHERE role = 'encargado_sede';
    END IF;
END $$;
