#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DEPLOY_PATH:-/srv/monstruo}"
BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:9000/health}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docs/deploy/docker-compose.yaml}"

echo "[deploy] dir=$APP_DIR branch=$BRANCH"
cd "$APP_DIR"

HAS_GIT_REPO=0
if [ -d "$APP_DIR/.git" ]; then
  HAS_GIT_REPO=1
fi

if [ "$HAS_GIT_REPO" = "1" ] && ! command -v git >/dev/null 2>&1; then
  echo "[deploy] ERROR: git no está instalado"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[deploy] ERROR: docker no está instalado"
  exit 1
fi

COMPOSE_BIN=()
if docker compose version >/dev/null 2>&1; then
  COMPOSE_BIN=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_BIN=(docker-compose)
else
  echo "[deploy] ERROR: docker compose no está disponible (ni 'docker compose' ni 'docker-compose')"
  exit 1
fi

if [ "$HAS_GIT_REPO" = "1" ]; then
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
else
  echo "[deploy] no git repo; asumiendo sync externo (runner)."
fi

echo "[deploy] compose up..."
if [ ! -f "$COMPOSE_FILE" ]; then
  echo "[deploy] ERROR: compose file no existe: $COMPOSE_FILE"
  exit 1
fi
"${COMPOSE_BIN[@]}" --project-directory "$APP_DIR" -f "$COMPOSE_FILE" up -d --build

echo "[deploy] health..."
for i in {1..30}; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[deploy] OK"
    exit 0
  fi
  sleep 2
done

echo "[deploy] ERROR: healthcheck falló: $HEALTH_URL"
"${COMPOSE_BIN[@]}" --project-directory "$APP_DIR" -f "$COMPOSE_FILE" ps || true
exit 1
