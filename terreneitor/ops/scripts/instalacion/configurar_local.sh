#!/bin/bash

# ops/scripts/setup_local_env.sh
# Script para configurar el entorno de desarrollo local (Laptop Legion)

echo "🛠️  Configurando entorno local para Terreneitor..."

# Navegar a la raíz del proyecto (3 niveles arriba)
cd "$(dirname "$0")/../../.." || exit

# 1. Crear VENV si no existe
if [ ! -d "code/venv" ]; then
    echo "📦 Creando entorno virtual Python (code/venv)..."
    python3 -m venv code/venv
else
    echo "✅ Entorno virtual ya existe."
fi

# 2. Instalar dependencias
echo "📥 Instalando librerías..."
source code/venv/bin/activate
pip install --upgrade pip
pip install -r config/requirements.txt

# 3. Instalar Git Hooks
echo "🪝  Configurando Guardianes (Git Hooks)..."
# Le decimos a pre-commit donde esta su config
pre-commit install --config config/.pre-commit-config.yaml

echo ""
echo "✨ ¡Listo! Tu Legion está preparada."
echo "   Para activar el entorno: source code/venv/bin/activate"
echo "   Para correr tests: pytest code/tests"
