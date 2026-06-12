#!/bin/bash

# Script de Despliegue Rápido para Terreneitor

echo "🚀 Iniciando despliegue de Terreneitor..."

# Navegar a la raíz del proyecto (3 niveles arriba)
cd "$(dirname "$0")/../../.." || exit

# 1. Verificar si Docker está corriendo
if ! docker info > /dev/null 2>&1; then
  echo "❌ Error: Docker no está corriendo o no tienes permisos."
  exit 1
fi

# 2. Reconstruir imagen (si hubo cambios en codigo)
echo "📦 Construyendo imagen optimizada..."
docker-compose --env-file ops/environments/.env -f docker/docker-compose.yml build

# 3. Reiniciar contenedores
echo "♻️  Reiniciando servicios..."
docker-compose --env-file ops/environments/.env -f docker/docker-compose.yml down
docker-compose --env-file ops/environments/.env -f docker/docker-compose.yml up -d

echo "✅ Despliegue completado."
echo "📜 Logs en vivo (Ctrl+C para salir):"
docker-compose --env-file ops/environments/.env -f docker/docker-compose.yml logs -f
