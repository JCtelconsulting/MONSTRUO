# Sync diario de planillas Fundación — instalación del timer

Estos dos archivos arman un cron diario (3 AM) que ejecuta el sync de las 7 planillas de Google Drive contra la DB de Fundación.

## Archivos

| Archivo | Para qué |
|---|---|
| `fundacion-sync-sheets.service` | Job oneshot que llama al script dentro del container |
| `fundacion-sync-sheets.timer` | Dispara el job todos los días a las 3:00 AM hora del servidor |

## Instalación (una sola vez)

```bash
sudo cp /srv/monstruo_dev/plataforma/ops/systemd/fundacion-sync-sheets.service /etc/systemd/system/
sudo cp /srv/monstruo_dev/plataforma/ops/systemd/fundacion-sync-sheets.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fundacion-sync-sheets.timer
```

## Verificar

```bash
# Ver cuándo corre la próxima vez
systemctl list-timers fundacion-sync-sheets.timer

# Forzar una corrida manual (sin esperar a las 3 AM)
sudo systemctl start fundacion-sync-sheets.service

# Ver logs
journalctl -u fundacion-sync-sheets.service --since today
```

## Equivalente cron clásico (alternativa)

Si prefieres `cron` en lugar de systemd, agrega a `/etc/cron.d/monstruo-fundacion-sync`:

```cron
0 3 * * * root /usr/bin/docker exec monstruo-dev-fundacion python -m fundacion.scripts.sync_sheets --trigger cron >> /var/log/fundacion-sync.log 2>&1
```

## Validar manualmente sin esperar

```bash
docker exec monstruo-dev-fundacion python -m fundacion.scripts.sync_sheets --trigger manual
```
