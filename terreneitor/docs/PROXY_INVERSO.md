# Configuración del Proxy Inverso (Terreneitor)

Este documento explica cómo está configurada la arquitectura de red y el proxy inverso para la aplicación.

## Arquitectura de Red

La configuración ha sido consolidada. En lugar de correr en tándem, todo el enrutamiento HTTPS (SSL) y mapeo de subdominios (`*.telconsulting.cl`) es manejado exclusivamente por una **Máquina Virtual de Proxy Inverso dedicada**, la cual redirige todo el tráfico hacia el contenedor Docker de Terreneitor directamente.

- **App Terreneitor (Docker Node):** `192.168.60.5` (Puerto expuesto: `8005`)
- **Proxy Inverso Nginx (VM Dedicada):** `192.168.60.6`

### Detalles Administrativos del Proxy Externa

- **IP de Conexión:** `192.168.60.6`
- **Autenticación (Usuario/Pass):** `root` / `Apstref.8`
- **Archivo de Configuración:** `/etc/nginx/sites-available/terreneitor.conf`

### Cómo Funciona el Flujo
1. El usuario accede a `https://terreneitor.telconsulting.cl` desde internet.
2. La solicitud llega a la IP Pública y es enrutada internamente hacia la VM `192.168.60.6` (Proxy).
3. El Nginx del proxy verifica certificados SSL y procesa reglas de subdominio (Dev/Prod).
4. El proxy hace un `proxy_pass` apuntando a la IP y puerto internos de la aplicación Dockerizada: `http://192.168.60.5:8005`.

### Nginx Local (Host 192.168.60.5)
El servidor Nginx corriendo en esta misma máquina (`192.168.60.5`) **fue DESHABILITADO** para Terreneitor. Sus configuraciones locales (`terreneitor_local.conf` y `terreneitor_local_dev.conf`) fueron removidas de `/etc/nginx/sites-enabled/` para evitar doble proxy y conflictos de puertos. Sigue corriendo exclusivamente para las conexiones o apps que dependan de él localmente (ej. Monstruo).
