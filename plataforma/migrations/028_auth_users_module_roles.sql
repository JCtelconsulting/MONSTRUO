-- auth.users.module_roles — rol específico POR MÓDULO (JSON dict).
--
-- Permite que un usuario tenga un rol distinto al global dentro de un módulo
-- que maneja roles propios. Hoy lo usa Terreneitor: en vez de derivar el rol
-- (TERRENO/SUPERVISOR/GERENCIA) del rol global del gateway, se elige explícito
-- al asignar el módulo en el modal de usuarios.
--
-- Formato: {"terreneitor": "SUPERVISOR"}  (módulo -> rol dentro de ese módulo)
-- Vacío ('{}')  => comportamiento previo (rol derivado del rol global).

ALTER TABLE auth.users
    ADD COLUMN IF NOT EXISTS module_roles TEXT DEFAULT '{}';
