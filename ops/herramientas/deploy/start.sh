#!/bin/bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/srv/monstruo_dev}"
PORT="${PORT:-9000}"

cd "$PROJECT_ROOT/code"
# Activar venv si existe (prioridad: local > root)
if [ -d "venv" ]; then
    source venv/bin/activate
fi
# Ejecutar Uvicorn en puerto 9000 (reload activo para dev)
if [ -f "venv/bin/python3" ]; then
    exec ./venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
elif command -v python3 >/dev/null 2>&1; then
    exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
else
    echo "ERROR: python3 no encontrado"
    exit 1
fi
