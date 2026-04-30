# GTA — Migraciones

Archivos SQL versionados para el schema `gta` en PostgreSQL.

## Convención de nombres

```
NNN_descripcion_corta.sql
```

- `NNN`: número secuencial de 3 dígitos (`001`, `002`, `003`…)
- Las migraciones se ejecutan **en orden** y **una sola vez**
- Nunca modificar un archivo ya ejecutado en producción — crear uno nuevo

## Archivos

| Archivo | Descripción |
| ------- | ----------- |
| `001_initial.sql` | Schema inicial: procesos, solicitudes, comentarios, quiebres |

## Cómo ejecutar (manual mientras no hay runner)

```bash
docker exec -i monstruo-dev-db psql -U monstruo -d monstruo_dev < gta/migrations/001_initial.sql
```
