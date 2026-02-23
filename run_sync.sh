#!/bin/bash
# Ejecuta el script de sincronización DENTRO del contenedor para tener acceso a la red interna y variables de entorno correctas.
docker exec -e PYTHONPATH=/app monstruo-dev-api python3 -u /app/code/scripts/sync_erp.py --days 60 --verbose
