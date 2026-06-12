-- Limpieza de tablas Jira/parallel — paralelo Jira+MONSTRUO nunca se ejecutó.
-- Drop seguro: IF EXISTS no falla si la tabla nunca se creó (entornos limpios).
-- Idempotente: se puede correr varias veces.

DROP TABLE IF EXISTS ops.parallel_decisions;
DROP TABLE IF EXISTS ops.parallel_kpi_daily;
DROP TABLE IF EXISTS ops.jira_sync_cursor;
DROP TABLE IF EXISTS ops.jira_sync_runs;
DROP TABLE IF EXISTS ops.jira_issue_map;
DROP TABLE IF EXISTS ops.jira_import_runs;
