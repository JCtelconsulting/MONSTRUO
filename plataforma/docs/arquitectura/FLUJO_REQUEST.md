# Documentación del Flujo de Peticiones (Request Flow)

> **AVISO (2026-06-12):** documento CONCEPTUAL. Los puertos/IPs/backends de hoy
> están en [../PROXY_INVERSO.md](../PROXY_INVERSO.md) y [ARQUITECTURA.md](ARQUITECTURA.md);
> los ejemplos de esta página pueden estar viejos.

Este documento explica cómo una petición viaja desde el navegador del usuario hasta los servicios de backend en el entorno de desarrollo de Monstruo.

## Componentes Principales

1.  **Servidor Proxy Inverso (Nginx):** Es el punto de entrada para todo el tráfico. Escucha en los dominios públicos (ej. `login.telconsulting.cl`) y decide a qué servicio de backend enviar la petición.
    *   **IP:** `192.168.60.6` (según lo indicado por el usuario)
    *   **Configuración:** `/etc/nginx/sites-available/`

2.  **Host de Docker:** Es la máquina que ejecuta los contenedores de Docker con los servicios de la aplicación.
    *   **IP:** `192.168.60.5` (según la configuración de Nginx)

3.  **Servicios Docker:** Son los contenedores que ejecutan la lógica de la aplicación (gateway, ticketera, etc.). Están definidos en el archivo `docker-compose.yaml`.

## Flujo General de una Petición Web (Ej: `login.telconsulting.cl/dev`)

1.  **Usuario -> Navegador:** El usuario introduce `https://login.telconsulting.cl/dev` en su navegador.

2.  **Navegador -> DNS:** El dominio `login.telconsulting.cl` se resuelve a la IP del servidor Nginx (`192.168.60.6`).

3.  **Navegador -> Nginx:** El navegador envía una petición HTTPS a Nginx.

4.  **Nginx -> Servicio Gateway:** Nginx procesa la petición. La configuración en `login.telconsulting.cl.conf` tiene un bloque `location` que coincide con la ruta `/dev/`:
    ```nginx
    location /dev/ {
        proxy_pass http://192.168.60.5:9001/;
        # ... otros headers ...
    }
    ```
    Nginx reenvía la petición al **Host de Docker** (`192.168.60.5`) en el puerto `9001`.

5.  **Docker Host -> Contenedor Gateway:** El Host de Docker tiene una regla de mapeo de puertos definida en `docker-compose.yaml` para el servicio `gateway`:
    ```yaml
    services:
      gateway:
        ports:
          - "${GATEWAY_PORT:-9001}:9001"
    ```
    Docker redirige la petición del puerto `9001` del host al puerto `9001` del contenedor `monstruo-dev-gateway`.

6.  **Respuesta:** El servicio `gateway` procesa la petición (sirviendo el HTML de la aplicación de login) y la respuesta viaja de vuelta por el mismo camino hasta el navegador del usuario.

## Flujo de una Petición de API (Ej: Ticketera)

1.  **Frontend -> API:** La aplicación web (ejecutándose en el navegador) realiza una llamada de API, por ejemplo a `https://login.telconsulting.cl/dev/api/tks/tickets`.

2.  **Nginx -> Servicio Ticketera:** Nginx recibe la petición. La configuración `login.telconsulting.cl.conf` tiene un bloque más específico que coincide con `/dev/api/tks/`:
    ```nginx
    location /dev/api/tks/ {
        proxy_pass http://192.168.60.5:9005/api/tks/;
        # ... otros headers ...
    }
    ```
    Nginx reenvía la petición al **Host de Docker** (`192.168.60.5`) en el puerto `9005`.

3.  **Docker Host -> Contenedor Ticketera:** El `docker-compose.yaml` tiene una regla de mapeo para el servicio `ticketera`:
    ```yaml
    services:
      ticketera:
        ports:
          - "9005:9005"
    ```
    Docker redirige la petición del puerto `9005` del host al puerto `9005` del contenedor `monstruo-dev-ticketera`.

4.  **Respuesta:** El servicio `ticketera` procesa la llamada de API y devuelve los datos (ej. en formato JSON) por el mismo camino de vuelta.

Este flujo desacoplado permite que cada servicio se ejecute de forma independiente, y el proxy inverso actúa como un controlador de tráfico inteligente, dirigiendo cada petición al lugar correcto.