# Ia — Migraciones

Archivos SQL versionados para el schema `ia` en PostgreSQL.

## Convención de nombres

```
NNN_descripcion_corta.sql
```

- `NNN`: número secuencial de 3 dígitos (`001`, `002`…)
- Las migraciones se ejecutan **en orden** y **una sola vez**
- Nunca modificar un archivo ya ejecutado en producción — crear uno nuevo

## Cómo ejecutar (manual mientras no hay runner)

```bash
docker exec -i monstruo-dev-db psql -U monstruo -d monstruo_dev < ia/migrations/NNN_nombre.sql
```
