-- Migración de prueba 001
-- Crea una tabla de prueba para validar el motor de migraciones
CREATE TABLE IF NOT EXISTS core.test_migration_table (
    id SERIAL PRIMARY KEY,
    test_value TEXT DEFAULT 'Motor operativo',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
