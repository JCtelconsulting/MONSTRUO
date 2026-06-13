# Proxy Inverso (Terreneitor)

> **Canónico:** el detalle del proxy (VM, upstreams PROD/DEV, dominios,
> sincronización repo↔VM) vive en
> [`../../plataforma/docs/arquitectura/PROXY_INVERSO.md`](../../plataforma/docs/arquitectura/PROXY_INVERSO.md)
> del repo Monstruo. Este archivo solo deja la nota específica de Terreneitor.

## Resumen Terreneitor

Todo el enrutamiento HTTPS (SSL) y los subdominios `*.telconsulting.cl` los
maneja la VM de proxy inverso dedicada `192.168.60.6`, que hace `proxy_pass` al
backend de Terreneitor.

- **DEV:** Terreneitor corre como módulo del ecosistema en el contenedor
  `monstruo-dev-terreneitor` (`192.168.60.8:8005`). La URL única es
  `terreneitor.telconsulting.cl`; portal/supervisor/gerencial/terreno redirigen
  307 desde la app (el proxy no necesitó cambios).
- **PROD:** sigue legado en `192.168.60.5` hasta su migración (ver
  [`MIGRACION_MONSTRUO.md`](MIGRACION_MONSTRUO.md)).
- Archivo de configuración en la VM: `/etc/nginx/sites-available/terreneitor.conf`
  (copia versionada en `plataforma/ops/nginx/terreneitor.conf`).

> Las credenciales de acceso al proxy **no van en el repo**: viven en
> `plataforma/ops/secrets/` (o en el gestor de secretos del equipo).
