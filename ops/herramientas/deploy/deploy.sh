#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DEPLOY_PATH:-/srv/monstruo}"
BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:9000/health}"

echo "[deploy] dir=$APP_DIR branch=$BRANCH"
cd "$APP_DIR"

if ! command -v git >/dev/null 2>&1; then
  echo "[deploy] ERROR: git no está instalado"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[deploy] ERROR: docker no está instalado"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[deploy] ERROR: docker compose no está disponible"
  exit 1
fi

echo "[deploy] fetch..."
git fetch origin "$BRANCH" --prune

echo "[deploy] checkout/reset..."
git checkout -q "$BRANCH"
git reset --hard "origin/$BRANCH"

# Limpieza segura: NO borrar env/local data
echo "[deploy] clean..."
git clean -fd \
  -e ".env" \
  -e ".env.*" \
  -e "data/" \
  -e "backups/" \
  -e "logs/" \
  -e "cache/" \
  -e "monstruo.db" \
  -e "*.sqlite" \
  -e "*.sqlite3" \
  -e "*.db"

echo "[deploy] compose up..."
docker compose up -d --build

echo "[deploy] health..."
for i in {1..30}; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[deploy] OK"
    exit 0
  fi
  sleep 2
done

echo "[deploy] ERROR: healthcheck falló: $HEALTH_URL"
docker compose ps || true
exit 1

