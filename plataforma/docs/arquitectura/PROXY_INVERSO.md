# Proxy Inverso

> **Última sincronización repo ↔ VM**: 2026-05-05. Hashes verificados byte a byte.

## VM proxy

`192.168.60.6` (hostname `PROXYSSL`). Nginx `1.22.1` con TLS por Let's Encrypt.

Configuración activa en `/etc/nginx/sites-enabled/`:

- `monstruo.conf` — toda la familia Monstruo (PROD + DEV)
- `terreneitor.conf` — Terreneitor (PROD + DEV)
- `sapa.conf` — Sapa
- `ultron.conf` — Ultron (puente a `192.168.20.228:5173`)

**Fuente de verdad versionada**: `plataforma/ops/nginx/` en el repo. Los 4 archivos del repo deben ser idénticos byte a byte a los de la VM. Cualquier cambio se hace en el repo y se sincroniza, nunca al revés.

## Backends reales (validados desde la VM)

### Upstreams Monstruo PROD

| Upstream | Backend |
|---|---|
| `monstruo_prod_ticketera_app` | `192.168.60.5:9001` |
| `monstruo_prod_login_app` | `192.168.60.5:9001` |
| `monstruo_prod_config_app` | `192.168.60.5:9001` |
| `monstruo_prod_ticketera_api` | `192.168.60.5:9005` |
| `monstruo_prod_fundacion_api` | `192.168.60.5:9006` |

### Upstreams Monstruo DEV

| Upstream | Backend |
|---|---|
| `monstruo_dev_base_app` | `192.168.60.8:9001` |
| `monstruo_dev_ticketera_api` | `192.168.60.8:9005` |
| `monstruo_dev_fundacion_api` | `192.168.60.8:9006` |
| `monstruo_dev_ia_app` | `192.168.20.228:18789` |
| `monstruo_dev_ia_oficina` | `192.168.20.228:8000` |

> **Nota importante**: PROD ya usa `9001/9005/9006`. La migración desde `9000` (modelo viejo) ya se completó en el proxy. Confirmar que las apps en `192.168.60.5` también escuchen en esos puertos.

## Dominios servidos

### Monstruo (`monstruo.conf`)

| Dominio | Comportamiento |
|---|---|
| `ticketera.telconsulting.cl` | PROD `/` → app+api ticketera. DEV `/dev/` → base + api+tks + fundacion |
| `login.telconsulting.cl` | PROD `/` → login. DEV `/dev/` → base + auth/google + sesion + tks + fundacion |
| `config.telconsulting.cl` | PROD `/` → config. DEV `/dev/` → base + tks |
| `ia.telconsulting.cl` | DEV `/dev/` → ia-app, `/dev/oficina/` → ia-oficina |
| `pmo.telconsulting.cl` | server_name declarado (verificar si tiene proxy_pass real o stub) |
| `erp.telconsulting.cl` | idem |
| `crm.telconsulting.cl` | idem |
| `bodega.telconsulting.cl` | idem |
| `zabbix.telconsulting.cl` | idem |
| `monitoreo.telconsulting.cl` | idem |

### Terreneitor (`terreneitor.conf`)

| Dominio | Backend PROD | Backend DEV |
|---|---|---|
| `terreneitor.telconsulting.cl` | `192.168.60.5:8080` | `192.168.60.5:8081` |
| `portal.telconsulting.cl` | idem | idem |
| `gerencial.telconsulting.cl` | idem | idem |
| `supervisor.telconsulting.cl` | idem | idem |
| `terreno.telconsulting.cl` | idem | idem |

Regla pública: PROD usa `/`, DEV usa `/dev/`.

### Sapa (`sapa.conf`)

Sin cambios desde 2026-04. Servicio externo.

### Ultron (`ultron.conf`)

`ultron.telconsulting.cl` → `192.168.20.228:5173` (HMR habilitado para front-end Vite). Activo, NO eliminado.

## Histórico

En `/etc/nginx/sites-available/_disabled/` la VM conserva snapshots de migraciones previas:

- `monstruo_migracion_20260413_201613/`
- `terreneitor_migracion_20260413_203143/`

Hay también un `ultron.conf.bak` suelto en `sites-available/` que sería bueno mover a `_disabled/` o eliminar.

## Servicios de la VM

- `nginx` (activo)
- `ssh` (activo)
- `postfix` desactivado, no escucha en `25`.
- Procesos `node` locales en `127.0.0.1` corresponden a la capa de acceso remoto/editor, no al proxy web.

## Cómo sincronizar repo ↔ VM

```bash
# Bajar configs reales al repo (verifica primero que la VM tenga la versión buena):
ssh root@192.168.60.6 "cat /etc/nginx/sites-enabled/monstruo.conf"     > plataforma/ops/nginx/monstruo.conf
ssh root@192.168.60.6 "cat /etc/nginx/sites-enabled/terreneitor.conf"  > plataforma/ops/nginx/terreneitor.conf
ssh root@192.168.60.6 "cat /etc/nginx/sites-enabled/sapa.conf"         > plataforma/ops/nginx/sapa.conf
ssh root@192.168.60.6 "cat /etc/nginx/sites-enabled/ultron.conf"       > plataforma/ops/nginx/ultron.conf

# Verificar hashes:
ssh root@192.168.60.6 "sha256sum /etc/nginx/sites-enabled/*.conf"
sha256sum plataforma/ops/nginx/*.conf

# Subir un cambio del repo a la VM (ejemplo monstruo.conf):
scp plataforma/ops/nginx/monstruo.conf root@192.168.60.6:/etc/nginx/sites-enabled/monstruo.conf
ssh root@192.168.60.6 "nginx -t && systemctl reload nginx"
```

## Reglas de mantenimiento

- Cualquier cambio se hace en el repo y se sincroniza a la VM, nunca al revés.
- Auditar la sincronización con `sha256sum` antes y después de cada cambio.
- Lo viejo va a `_disabled/` en la VM, no se deja como `.bak` suelto en `sites-enabled/` o `sites-available/`.
- Una sola familia de aplicación por archivo `.conf`. No volver a configs separados por dominio.
- Documentar este archivo cada vez que se agrega/quita un dominio o un upstream.

## Pendientes conocidos

- Mover `ultron.conf.bak` (suelto en `sites-available/` de la VM) a `_disabled/` o eliminarlo.
- Confirmar si los dominios `pmo`, `erp`, `crm`, `bodega`, `zabbix`, `monitoreo` declarados en `monstruo.conf` tienen `proxy_pass` real o son stubs esperando backend.
