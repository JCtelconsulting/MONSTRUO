# Operaciones Terreneitor (`/ops`)

Esta carpeta centraliza todos los scripts y configuraciones necesarias para la operación, mantenimiento y despliegue de la aplicación.

## Estructura

- **`scripts/`**: Scripts ejecutables.
    - `backup/`: Sistema de respaldos (`terreneitor_backup.sh`) y servicios systemd.
    - `mantenimiento/`: Scripts de limpieza y calidad.
    - `herramientas/`: Utilerías CLI como `puente_cli.py`.
    - `debug/`: Scripts para diagnóstico.
    - `entorno/`, `despliegue/`: Configuración de ambiente.

> [!TIP]
> Todos los scripts deben ser ejecutables desde la raíz del proyecto o auto-detectar su ubicación.
