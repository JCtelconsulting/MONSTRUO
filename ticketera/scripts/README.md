# Ticketera — Scripts

Seed de tickets de prueba, exportación de SLA, limpieza de adjuntos huérfanos.

## Convención

- Nombrar con prefijo de acción: `seed_`, `export_`, `fix_`, `check_`
- Nunca correr scripts destructivos contra prod sin confirmación explícita
- Scripts Python: usar `python scripts/nombre.py` desde la raíz del repo
- Scripts Bash: `bash ticketera/scripts/nombre.sh`
