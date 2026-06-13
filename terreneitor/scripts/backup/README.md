# Backups Terreneitor (Google Drive)

Respalda DB + codigo + fotos a un Shared Drive de Google via rclone.

## Scripts

|Script|Entorno|BASE_DIR|
|---|---|---|
|`terreneitor_integral_backup_prod.sh`|**Produccion**|`/srv/terreneitor`|
|`terreneitor_integral_backup_dev.sh`|**Desarrollo**|`/srv/terreneitor_dev`|

Ambos hacen lo mismo (DB + tar.gz del codigo + sync de fotos a Drive). Solo cambian las rutas y los nombres de los archivos remotos.

## Programacion (cron del usuario `juan`)

```cron
# Dev: una vez al dia, 03:00
0 3 * * * flock -n /tmp/terreneitor-dev-backup.lock bash /srv/terreneitor/ops/scripts/backup/terreneitor_integral_backup_dev.sh >> /srv/terreneitor_dev/logs/backup.log 2>&1

# Prod: dos veces al dia, 07:00 y 21:00
0 7,21 * * * flock -n /tmp/terreneitor-prod-backup.lock bash /srv/terreneitor/ops/scripts/backup/terreneitor_integral_backup_prod.sh >> /srv/terreneitor/logs/backup.log 2>&1
```

`flock` evita que se solapen ejecuciones si la anterior aun esta corriendo.

## Requisitos

- rclone instalado en el host.
- Config rclone en `/home/juan/.config/rclone/rclone.conf` con remoto llamado `Terreneitor` (Shared Drive).
- Permisos de lectura sobre la DB (`data/db/terreneitor.db`) y los archivos (`data/files/`).

## Ejecucion manual

```bash
bash /srv/terreneitor/ops/scripts/backup/terreneitor_integral_backup_prod.sh
# o
bash /srv/terreneitor/ops/scripts/backup/terreneitor_integral_backup_dev.sh
```

## Verificar ultimos backups

```bash
tail -30 /srv/terreneitor/logs/backup.log         # prod
tail -30 /srv/terreneitor_dev/logs/backup.log     # dev
ls -la /srv/terreneitor/data/backups/db_snapshots/  # snapshots locales recientes
```

## Estructura en Drive

- DB: `Terreneitor:Backups/db/db_prod_*.sqlite.gz` y `db_dev_*.sqlite.gz`
- Codigo: `Terreneitor:Backups/code/code_prod_*.tar.gz` y `code_dev_*.tar.gz`
- Fotos: `Terreneitor:Fotos/...` (sync diferencial)

## Nota historica

Hasta abril 2026 existia tambien una unidad systemd `terreneitor-backup.timer` que ejecutaba una variante mas simple (`terreneitor_backup.sh`) en horarios solapados al cron prod. Esa unidad apuntaba a una ruta inexistente y fallaba silenciosamente. Fue desinstalada y los archivos movidos a `_papelera_refactor/systemd_redundante/`. Hoy todo el sistema de backups corre por cron.
