-- Fundación — tabla de usuarios PROPIA (login independiente del gateway de Monstruo).
--
-- Separación fase 2: Fundación deja de autenticar contra auth.users (la tabla de
-- login de Monstruo) y pasa a su propia identidad en fundacion.users. Espeja las
-- columnas que usa el código de auth (auth_service / deps / login), sin la columna
-- `organizacion` (ya no aplica: esta tabla es 100% Fundación).
--
-- El scope por sede vive en fundacion.sede_membresias (versionado); la columna
-- fundacion_scope se conserva por compatibilidad con get_user_fundacion_scope.
--
-- En fase 3, sede_membresias.usuario_id dejará de referenciar auth.users(id) y
-- pasará a referenciar fundacion.users(id).

CREATE TABLE IF NOT EXISTS fundacion.users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'gestora_educativa',
    secondary_roles TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT,
    allowed_modules TEXT,
    fundacion_scope TEXT,
    first_name      TEXT,
    last_name       TEXT,
    phone_number    TEXT,
    module_roles    TEXT
);

CREATE INDEX IF NOT EXISTS idx_fundacion_users_username ON fundacion.users(username);
