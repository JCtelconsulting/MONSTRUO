-- Nueva columna gta.tareas.espera_devolucion_paso
--
-- Cuando se devuelve una tarea (paso N) a un paso destino (paso M, M < N),
-- la tarea actual queda 'devuelta' pero NO retoma cuando su dependencia
-- original cierra: tiene que esperar específicamente al paso destino.
--
-- Antes esto se hacía contaminando paso_depende_de, lo que mezclaba la
-- definición del flujo con un estado transitorio. Mejor: campo dedicado.
--
-- Cuando el paso `espera_devolucion_paso` se cierra → la tarea pasa a
-- 'pendiente' (o 'en_curso' si conserva responsable vigente) y el campo
-- se limpia.

ALTER TABLE gta.tareas
    ADD COLUMN IF NOT EXISTS espera_devolucion_paso INTEGER;

-- Lookup para reanudar tareas devueltas cuando cierra un paso predecesor.
CREATE INDEX IF NOT EXISTS idx_tareas_espera_devolucion
    ON gta.tareas(flujo_id, espera_devolucion_paso)
    WHERE espera_devolucion_paso IS NOT NULL;
