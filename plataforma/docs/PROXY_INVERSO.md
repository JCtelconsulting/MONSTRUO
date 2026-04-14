# Proxy Inverso

## Estado actual

La VM `192.168.60.6` quedó ordenada para funcionar como proxy inverso.

Configuración activa de Nginx:
- `monstruo.conf`
- `terreneitor.conf`
- `sapa.conf`

## Monstruo

### PROD

Activos hoy:
- `ticketera.telconsulting.cl`
- `login.telconsulting.cl`
- `config.telconsulting.cl`

Backend actual:
- `192.168.60.5:9000`

Regla pública:
- PROD usa `/`

Notas:
- `login/.../dashboard` entra por el bloque general de `login`
- `login/.../fundacion` entra por el bloque general de `login`

### DEV

DEV quedó modelado por servicios reales:
- `base-dev` -> `192.168.60.8:9001`
- `ticketera-api-dev` -> `192.168.60.8:9005`
- `ia-dev` -> `192.168.20.228:18789`
- `ia-oficina-dev` -> `192.168.20.228:8000`

Relación actual:
- `ticketera.telconsulting.cl`
  - `/dev/` -> `base-dev`
  - `/dev/api/` -> `base-dev`
  - `/dev/api/tks/` -> `ticketera-api-dev`
- `login.telconsulting.cl`
  - `/dev/` -> `base-dev`
  - `/dev/api/auth/` -> `base-dev`
  - `/dev/api/auth/google/` -> `base-dev`
  - `/dev/api/sesion` -> `base-dev`
  - `/dev/api/tks/` -> `ticketera-api-dev`
- `config.telconsulting.cl`
  - `/dev/` -> `base-dev`
  - `/dev/api/` -> `base-dev`
  - `/dev/api/tks/` -> `ticketera-api-dev`
- `ia.telconsulting.cl`
  - `/dev/` -> `ia-dev`
  - `/dev/oficina/` -> `ia-oficina-dev`

Pendientes:
- `ia.telconsulting.cl` en PROD
- `pmo.telconsulting.cl`
- `erp.telconsulting.cl`
- `crm.telconsulting.cl`
- `bodega.telconsulting.cl`
- `zabbix.telconsulting.cl`
- `monitoreo.telconsulting.cl`

## Terreneitor

Archivo activo:
- `terreneitor.conf`

Dominios incluidos:
- `terreneitor.telconsulting.cl`
- `portal.telconsulting.cl`
- `gerencial.telconsulting.cl`
- `supervisor.telconsulting.cl`
- `terreno.telconsulting.cl`

Backends actuales:
- PROD -> `192.168.60.5:8080`
- DEV -> `192.168.60.5:8081`

Regla pública:
- PROD usa `/`
- DEV usa `/dev/`

## Sapa

Archivo activo:
- `sapa.conf`

No se tocó en esta ronda.

## Limpieza realizada

Se eliminó del árbol activo:
- configs viejos separados de Monstruo
- configs viejos separados de Terreneitor
- `ultron.conf`
- snippets viejos de Monstruo

La VM del proxy quedó reducida a:
- `monstruo.conf`
- `terreneitor.conf`
- `sapa.conf`

## Servicios de la VM

Servicios relevantes:
- `nginx`
- `ssh`

`postfix` se desactivó y dejó de escuchar en `25`.

Los procesos `node` locales en `127.0.0.1` corresponden a la capa de acceso remoto/editor, no al proxy web.

## Validación

Validado después de ordenar Monstruo y Terreneitor:
- `nginx -t` OK
- reload OK
- `login` PROD OK
- `config` PROD OK
- `ticketera` PROD OK
- `terreneitor` PROD OK
- `portal` PROD OK
- `gerencial` PROD OK
- `supervisor` PROD OK
- `terreno` PROD OK
- todos los `/dev/` de Terreneitor OK

Pendiente conocido:
- `ticketera.telconsulting.cl/dev/` sigue devolviendo `500`
- eso apunta a backend DEV, no al proxy

## Regla de mantenimiento

Para no volver al desorden:
- unificar por familia de aplicación
- documentar `PROD` según lo que realmente está activo hoy
- documentar `DEV` por servicio real, no por arrastre histórico
- mover lo viejo a `_disabled` o eliminarlo
- evitar dejar archivos paralelos activos para la misma familia
