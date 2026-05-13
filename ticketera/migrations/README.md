# Ticketera — Migraciones

Archivos SQL versionados para el schema `tks` en PostgreSQL.

## Convención

`NNN_descripcion_corta.sql` — `NNN` secuencial de 3 dígitos. Las migraciones
se ejecutan en orden y una sola vez; no modificar archivos ya aplicados en
producción, crear uno nuevo.

## Aplicar (manual, mientras no haya runner)

```bash
docker exec -i <db-container> psql -U monstruo -d monstruo < ticketera/migrations/NNN_nombre.sql
```
