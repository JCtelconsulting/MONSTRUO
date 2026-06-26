#!/usr/bin/env bash
# Backup diario de la base de producción Monstruo (Postgres en el container monstruo-db).
#
# Uso:   ./backup-db.sh
# Cron:  0 3 * * *  /srv/monstruo/plataforma/ops/scripts/backup-db.sh >> /srv/monstruo/backups/backup.log 2>&1
#
# Genera un pg_dump comprimido de TODA la base, con rotación. Configurable por env:
#   MONSTRUO_BACKUP_DIR        (default /srv/monstruo/backups)
#   MONSTRUO_BACKUP_RETENTION  (días a conservar, default 14)
set -euo pipefail

BACKUP_DIR="${MONSTRUO_BACKUP_DIR:-/srv/monstruo/backups}"
RETENTION_DAYS="${MONSTRUO_BACKUP_RETENTION:-14}"
DB_CONTAINER="${MONSTRUO_DB_CONTAINER:-monstruo-db}"
DB_USER="${MONSTRUO_DB_USER:-monstruo}"
DB_NAME="${MONSTRUO_DB_NAME:-monstruo}"

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/monstruo_${TS}.sql.gz"

docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner | gzip > "$OUT"

# Un dump válido nunca es trivialmente chico; si quedó vacío, abortar y no rotar.
if [ ! -s "$OUT" ] || [ "$(stat -c%s "$OUT")" -lt 1024 ]; then
    echo "[backup-db] ERROR: dump vacío o demasiado chico ($OUT)" >&2
    rm -f "$OUT"
    exit 1
fi

echo "[backup-db] $(date '+%Y-%m-%d %H:%M:%S') OK -> $OUT ($(du -h "$OUT" | cut -f1))"

# Rotación: borrar backups más viejos que RETENTION_DAYS días.
find "$BACKUP_DIR" -name 'monstruo_*.sql.gz' -type f -mtime +"$RETENTION_DAYS" -delete
