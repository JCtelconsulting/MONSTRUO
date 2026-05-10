-- gta.flujo_adjuntos — archivos compartidos por todas las tareas de un flujo.
--
-- Modelo: los adjuntos son DEL FLUJO, no de una tarea individual. Cualquier
-- responsable de cualquier paso puede subir/ver, así el validador del paso 2
-- ve la PTE que cargó comercial en el paso 1, y compras ve la cotización del
-- paso 3 sin tener que pedirla.
--
-- Almacenamiento físico: gta/data/flujos/<flujo_id>/<filename>
-- En esta tabla queda el metadata + path relativo a gta/data/.

CREATE TABLE IF NOT EXISTS gta.flujo_adjuntos (
    id          SERIAL PRIMARY KEY,
    flujo_id    UUID NOT NULL,
    filename    TEXT NOT NULL,           -- nombre original (display)
    ruta        TEXT NOT NULL,           -- path relativo a gta/data/, ej: flujos/<uuid>/PTE.pdf
    mime        TEXT,
    size_bytes  BIGINT,
    subido_por  INTEGER REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Lookup por flujo (la query principal: "dame los adjuntos de este flujo")
CREATE INDEX IF NOT EXISTS idx_flujo_adjuntos_flujo_id ON gta.flujo_adjuntos(flujo_id);
