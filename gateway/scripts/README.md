# Gateway — Scripts

Gestión de sesiones, rebuild de imágenes, seed de usuarios.

## Convención

- Nombrar con prefijo de acción: `seed_`, `export_`, `fix_`, `check_`
- Nunca correr scripts destructivos contra prod sin confirmación explícita
- Scripts Python: usar `python scripts/nombre.py` desde la raíz del repo
- Scripts Bash: `bash gateway/scripts/nombre.sh`
