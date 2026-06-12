-- GTA — Rediseño de tareas: owner = subárea, asignación versionada
--
-- La tabla gta.tareas existente está vacía (0 filas en DEV al 2026-05-06),
-- así que la rediseñamos en lugar de migrar datos.
--
-- Schema viejo: tareas con asignado_a TEXT y creado_by TEXT (frágil ante
-- cambios de personal). Schema nuevo: subarea_id como owner, y
-- gta.tarea_participaciones versiona quién es responsable / co-responsable /
-- ayuda en cada momento.
--
-- Reglas:
--   - Una tarea pertenece a UNA subárea (subarea_id NOT NULL).
--   - Una tarea tiene 0 o 1 responsable VIGENTE a la vez.
--   - Una tarea puede tener N co-responsables y N "ayudas" simultáneas.
--   - Los cambios se reflejan cerrando filas (hasta=now()) y abriendo nuevas.

DROP TABLE IF EXISTS gta.tareas CASCADE;

CREATE TABLE gta.tareas (
    id              SERIAL PRIMARY KEY,
    subarea_id      INTEGER NOT NULL REFERENCES gta.subareas(id) ON DELETE RESTRICT,
    proceso_id      INTEGER REFERENCES gta.procesos(id) ON DELETE SET NULL,
    flujo_tarea_id  INTEGER REFERENCES gta.flujo_tareas(id) ON DELETE SET NULL,
    titulo          TEXT NOT NULL,
    descripcion     TEXT,
    tipo            TEXT,
    prioridad       TEXT NOT NULL DEFAULT 'media' CHECK (prioridad IN ('baja', 'media', 'alta', 'urgente')),
    estado          TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'en_curso', 'bloqueada', 'cerrada', 'cancelada')),
    sla_horas       INTEGER,
    sla_due_at      TIMESTAMP,
    fecha_inicio    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin       TIMESTAMP,
    creado_por      INTEGER NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    cerrado_por     INTEGER REFERENCES auth.users(id) ON DELETE SET NULL,
    cerrado_at      TIMESTAMP,
    reporte_cierre  TEXT,
    tags            TEXT NOT NULL DEFAULT '[]',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tareas_subarea_estado ON gta.tareas (subarea_id, estado);
CREATE INDEX idx_tareas_estado ON gta.tareas (estado);
CREATE INDEX idx_tareas_creado_por ON gta.tareas (creado_por);
CREATE INDEX idx_tareas_proceso ON gta.tareas (proceso_id) WHERE proceso_id IS NOT NULL;


-- Participaciones persona ↔ tarea (versionado, multi-rol) ─────────────────
CREATE TABLE IF NOT EXISTS gta.tarea_participaciones (
    id              SERIAL PRIMARY KEY,
    tarea_id        INTEGER NOT NULL REFERENCES gta.tareas(id) ON DELETE CASCADE,
    usuario_id      INTEGER NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rol             TEXT NOT NULL CHECK (rol IN ('responsable', 'co_responsable', 'ayuda')),
    desde           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hasta           TIMESTAMP,
    asignado_por    INTEGER REFERENCES auth.users(id) ON DELETE SET NULL,
    motivo          TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 1 responsable vigente por tarea
CREATE UNIQUE INDEX IF NOT EXISTS uq_participacion_responsable_vigente
    ON gta.tarea_participaciones (tarea_id)
    WHERE rol = 'responsable' AND hasta IS NULL;

-- No duplicar (tarea, usuario, rol) vigente — evita doble "ayuda" del mismo user
CREATE UNIQUE INDEX IF NOT EXISTS uq_participacion_user_rol_vigente
    ON gta.tarea_participaciones (tarea_id, usuario_id, rol)
    WHERE hasta IS NULL;

CREATE INDEX IF NOT EXISTS idx_participacion_tarea_vigente
    ON gta.tarea_participaciones (tarea_id)
    WHERE hasta IS NULL;

CREATE INDEX IF NOT EXISTS idx_participacion_usuario_vigente
    ON gta.tarea_participaciones (usuario_id)
    WHERE hasta IS NULL;


-- Helpers SQL ───────────────────────────────────────────────────────────
-- Responsable vigente de una tarea (NULL si no tiene)
CREATE OR REPLACE FUNCTION gta.responsable_vigente(p_tarea_id INTEGER)
RETURNS INTEGER AS $$
    SELECT usuario_id
    FROM gta.tarea_participaciones
    WHERE tarea_id = p_tarea_id
      AND rol = 'responsable'
      AND hasta IS NULL
    LIMIT 1;
$$ LANGUAGE SQL STABLE;

-- Participaciones vigentes de una tarea (todos los roles)
CREATE OR REPLACE FUNCTION gta.participantes_vigentes(p_tarea_id INTEGER)
RETURNS TABLE (usuario_id INTEGER, rol TEXT, desde TIMESTAMP) AS $$
    SELECT p.usuario_id, p.rol, p.desde
    FROM gta.tarea_participaciones p
    WHERE p.tarea_id = p_tarea_id
      AND p.hasta IS NULL
    ORDER BY
        CASE p.rol WHEN 'responsable' THEN 0 WHEN 'co_responsable' THEN 1 ELSE 2 END,
        p.desde;
$$ LANGUAGE SQL STABLE;
