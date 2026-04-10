#!/bin/bash
# Ejecuta el script de sincronización DENTRO del contenedor para tener acceso a la red interna y variables de entorno correctas.
docker exec -e PYTHONPATH=/app/erp:/app/plataforma/legacy/code monstruo-dev-erp python3 -u /app/plataforma/legacy/code/scripts/sync_erp.py --days 60 --verbose
