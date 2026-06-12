-- Limpieza de roles obsoletos de Fundación.
--
-- Roles canónicos del organigrama (los únicos válidos a partir de hoy):
--   directora_social, jefa_pedagogica, coordinadora_territorial,
--   lider_educativo, gestora_educativa.
--
-- Eliminamos:
--   - ejecutiva           (no está en el organigrama)
--   - fundacion           (rol genérico, redundante con los anteriores)
--   - encargado_<sede>    (legacy: 7 sedes, reemplazados por lider_educativo
--                          + scope vía fundacion.sede_membresias)
--
-- bmerino@acompanandopasos.cl pasa de admin a directora_social y se le
-- limpia el secondary_role 'ejecutiva' que tenía colgando.

-- 1. Limpiar permisos huérfanos en core.sys_role_permissions.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='core' AND table_name='sys_role_permissions'
    ) THEN
        DELETE FROM core.sys_role_permissions
        WHERE role IN (
            'ejecutiva',
            'fundacion',
            'encargado_la_pintana',
            'encargado_maipu',
            'encargado_llay_llay',
            'encargado_huechuraba',
            'encargado_renca',
            'encargado_lo_espejo',
            'encargado_cerro_navia',
            'encargado_sede',
            'monitora'
        );
    END IF;
END $$;

-- 2. Si algún usuario quedó con role primario en uno de estos roles muertos,
--    fallback a gestora_educativa (no debería pasar hoy, pero defensivo).
UPDATE auth.users
SET role = 'gestora_educativa'
WHERE role IN (
    'ejecutiva', 'fundacion',
    'encargado_la_pintana', 'encargado_maipu', 'encargado_llay_llay',
    'encargado_huechuraba', 'encargado_renca', 'encargado_lo_espejo',
    'encargado_cerro_navia', 'encargado_sede', 'monitora'
);

-- 3. bmerino: admin → directora_social (es la directora social).
UPDATE auth.users
SET role = 'directora_social'
WHERE username = 'bmerino@acompanandopasos.cl';

-- 4. Limpiar 'ejecutiva', 'fundacion' y 'encargado_*' de secondary_roles.
--    secondary_roles es JSON-en-texto. Reemplazamos las ocurrencias exactas
--    (envueltas en comillas) y luego compactamos comas duplicadas y arrays
--    que queden tipo ["", ...].
UPDATE auth.users
SET secondary_roles = COALESCE(secondary_roles, '[]')
WHERE secondary_roles IS NULL;

-- Eliminar cada rol muerto del JSON (estrategia simple: reemplazar el
-- string con comillas, luego compactar).
UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"ejecutiva"', '')
WHERE secondary_roles LIKE '%"ejecutiva"%';

UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"fundacion"', '')
WHERE secondary_roles LIKE '%"fundacion"%';

UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"encargado_la_pintana"', '')
WHERE secondary_roles LIKE '%"encargado_la_pintana"%';
UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"encargado_maipu"', '')
WHERE secondary_roles LIKE '%"encargado_maipu"%';
UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"encargado_llay_llay"', '')
WHERE secondary_roles LIKE '%"encargado_llay_llay"%';
UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"encargado_huechuraba"', '')
WHERE secondary_roles LIKE '%"encargado_huechuraba"%';
UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"encargado_renca"', '')
WHERE secondary_roles LIKE '%"encargado_renca"%';
UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"encargado_lo_espejo"', '')
WHERE secondary_roles LIKE '%"encargado_lo_espejo"%';
UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"encargado_cerro_navia"', '')
WHERE secondary_roles LIKE '%"encargado_cerro_navia"%';
UPDATE auth.users
SET secondary_roles = REPLACE(secondary_roles, '"encargado_sede"', '')
WHERE secondary_roles LIKE '%"encargado_sede"%';

-- Compactar el JSON: ", ," → "," ; "[, " → "[" ; ", ]" → "]" ; arrays
-- vacíos huecos quedan como "[]".
UPDATE auth.users
SET secondary_roles = regexp_replace(
    regexp_replace(
        regexp_replace(
            regexp_replace(secondary_roles, ',\s*,', ',', 'g'),
            '\[\s*,', '[', 'g'
        ),
        ',\s*\]', ']', 'g'
    ),
    '\[\s*\]', '[]', 'g'
)
WHERE secondary_roles IS NOT NULL;
