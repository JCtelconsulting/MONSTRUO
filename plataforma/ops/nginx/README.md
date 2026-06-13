# Nginx versionado

Este directorio guarda la copia versionada de la configuración activa del proxy inverso.

Archivos actuales:
- `monstruo.conf`
- `terreneitor.conf`
- `sapa.conf`

Origen actual:
- VM proxy `192.168.60.6`
- ruta remota `/etc/nginx/sites-available/`

## Regla

Cuando se cambie el proxy real, este directorio debe actualizarse.

No debe volver a existir una diferencia silenciosa entre:
- lo que está activo en la VM proxy
- lo que está versionado en el repo

Sincronización mínima:
- cambiar en la VM proxy
- validar con `nginx -t`
- copiar el `conf` actualizado a este directorio
- registrar el cambio en `plataforma/docs/arquitectura/PROXY_INVERSO.md`

## Referencia

Descripción operativa:
- [../../docs/arquitectura/PROXY_INVERSO.md](../../docs/arquitectura/PROXY_INVERSO.md)
