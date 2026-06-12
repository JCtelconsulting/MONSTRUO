-- auth.users.organizacion — separación lógica Monstruo / Fundación
--
-- Aísla a los usuarios de Fundación de los de Monstruo a nivel de gestión.
-- No es un mecanismo de autenticación: todos siguen en la misma tabla y
-- comparten el login. Es un atributo de "a qué organización pertenece este
-- usuario", usado por las UIs de gestión para filtrar.
--
-- Regla de backfill (acordada con el usuario):
--   - allowed_modules contiene 'fundacion' Y NO contiene módulos de Monstruo
--     (tks, gta, crm, erp, pmo, ia, bodega, zabbix, config) → 'fundacion'
--   - el resto → 'monstruo' (incluye los puente, ej. sistemas@telconsulting.cl)
--
-- bmerino@acompanandopasos.cl pasa de 'monitora' a 'admin' (admin de Fundación).

ALTER TABLE auth.users
    ADD COLUMN IF NOT EXISTS organizacion TEXT NOT NULL DEFAULT 'monstruo';

ALTER TABLE auth.users
    DROP CONSTRAINT IF EXISTS users_organizacion_chk;

ALTER TABLE auth.users
    ADD CONSTRAINT users_organizacion_chk
    CHECK (organizacion IN ('monstruo', 'fundacion'));

CREATE INDEX IF NOT EXISTS idx_users_organizacion ON auth.users (organizacion);


-- Backfill: marcar como 'fundacion' a usuarios cuyo allowed_modules contenga
-- 'fundacion' y NO contenga ningún módulo Monstruo.
WITH parsed AS (
    SELECT
        id,
        username,
        COALESCE(allowed_modules, '[]') AS am
    FROM auth.users
)
UPDATE auth.users u
SET organizacion = 'fundacion'
FROM parsed p
WHERE u.id = p.id
  AND p.am LIKE '%"fundacion"%'
  AND p.am NOT LIKE '%"tks"%'
  AND p.am NOT LIKE '%"gta"%'
  AND p.am NOT LIKE '%"crm"%'
  AND p.am NOT LIKE '%"erp"%'
  AND p.am NOT LIKE '%"pmo"%'
  AND p.am NOT LIKE '%"ia"%'
  AND p.am NOT LIKE '%"bodega"%'
  AND p.am NOT LIKE '%"zabbix"%'
  AND p.am NOT LIKE '%"config"%';

-- Promover a admin a quien hoy sea monitora dentro de Fundación.
-- (Caso conocido: bmerino@acompanandopasos.cl). Se aplica solo si el rol
-- es 'monitora' para no pisar otros roles en el futuro.
UPDATE auth.users
SET role = 'admin'
WHERE organizacion = 'fundacion'
  AND role = 'monitora';
