#!/bin/bash
export PORT=9000
cd /srv/monstruo/code
# Activar venv si existe (prioridad: local > root)
if [ -d "venv" ]; then
    source venv/bin/activate
fi
# Ejecutar Uvicorn en puerto 9000 (reload activo para dev)
# Note: we are in sistema_gestion/ now
if [ -f "venv/bin/python3" ]; then
    exec ./venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
else
    echo "ERROR: python3 no encontrado en venv"
    exit 1
fi
