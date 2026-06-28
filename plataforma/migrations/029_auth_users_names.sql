-- auth.users.first_name / last_name — nombre y apellido reales del usuario.
--
-- Hasta ahora el nombre de una persona se DERIVABA del correo
-- (juan.lopez@x -> "Juan Lopez"), lo que daba nombres incompletos o raros.
-- Estos campos permiten cargar el nombre real desde la gestión de usuarios.
--
-- La identidad central (auth) es la única fuente del nombre: cada módulo lo
-- consume vía la sesión / el directorio de usuarios y, si está vacío, cae al
-- fallback de derivar del correo. Contrato hacia los módulos: display_name =
-- "{first_name} {last_name}".trim() (puede venir vacío).
--
-- Backfill: NO se hace. Los usuarios sin nombre quedan con '' y los módulos
-- aplican el fallback. Cargar el nombre es una acción manual del admin.

ALTER TABLE auth.users
    ADD COLUMN IF NOT EXISTS first_name TEXT DEFAULT '';

ALTER TABLE auth.users
    ADD COLUMN IF NOT EXISTS last_name TEXT DEFAULT '';
