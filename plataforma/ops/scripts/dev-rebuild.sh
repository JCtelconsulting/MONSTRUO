#!/usr/bin/env bash
# Rebuild de containers DEV con cache-busting garantizado.
#
# Por qué existe:
#   - El gateway inyecta `window.ASSET_VERSION` en cada HTML servido para
#     romper el cache del browser cuando hay cambios en JS/CSS.
#   - Esa versión se computa desde la variable de entorno ASSET_VERSION
#     (ver plataforma/core/version.py), y si no está, fallback al SHA del
#     último commit. PERO el container no tiene .git, así que ese fallback
#     no aplica — termina usando el timestamp del archivo version.py, que
#     SOLO cambia si modificás ese archivo.
#   - Resultado: cuando trabajás en cambios sin commit, el browser se queda
#     con el JS/CSS viejo aunque rebuildees el container. Bug clásico.
#
# Solución: este script siempre exporta ASSET_VERSION="dev-<timestamp>"
# antes de hacer `docker compose up --build`, así cada rebuild es único y
# el browser se ve forzado a recargar todos los assets.
#
# Uso:
#   ./plataforma/ops/scripts/dev-rebuild.sh                   # rebuild todos
#   ./plataforma/ops/scripts/dev-rebuild.sh gateway gta       # rebuild solo gateway+gta
#
# En PROD: NO usar este script. PROD debe usar el SHA del commit como
# ASSET_VERSION (que se setea en el deploy formal con CI/CD).

set -euo pipefail

# El script vive en plataforma/ops/scripts/, raíz del repo a 3 niveles arriba
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

# Si el árbol está limpio (sin cambios sin commit), usamos el SHA del commit.
# Si está sucio, agregamos timestamp para garantizar cache-bust único.
if git diff-index --quiet HEAD -- 2>/dev/null && [ -z "$(git status --porcelain 2>/dev/null)" ]; then
    SHA="$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
    ASSET_VERSION="$SHA"
    echo "→ Árbol limpio, usando SHA del commit: $ASSET_VERSION"
else
    SHA="$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
    ASSET_VERSION="$SHA-$(date +%s)"
    echo "→ Árbol con cambios sin commit, usando: $ASSET_VERSION"
fi

export ASSET_VERSION
export APP_UID="$(id -u)"
export APP_GID="$(id -g)"

CONTAINERS=("$@")
if [ ${#CONTAINERS[@]} -eq 0 ]; then
    echo "→ Rebuild de TODOS los containers"
    docker compose --env-file plataforma/ops/env/.env.server.dev up -d --build
else
    echo "→ Rebuild de: ${CONTAINERS[*]}"
    docker compose --env-file plataforma/ops/env/.env.server.dev up -d --build "${CONTAINERS[@]}"
fi

echo ""
echo "ASSET_VERSION en uso: $ASSET_VERSION"
echo "→ Hacé F5 normal en el browser, no necesitás hard reload."
