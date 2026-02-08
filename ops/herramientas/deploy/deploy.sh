#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DEPLOY_PATH:-/srv/monstruo}"
BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:9000/health}"
DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-}"

DEFAULT_COMPOSE_FILE="$APP_DIR/docker-compose.yaml"
LEGACY_COMPOSE_FILE="$APP_DIR/docs/deploy/docker-compose.yaml"
if [ -n "${COMPOSE_FILE:-}" ]; then
  COMPOSE_FILE="$COMPOSE_FILE"
elif [ -f "$DEFAULT_COMPOSE_FILE" ]; then
  COMPOSE_FILE="$DEFAULT_COMPOSE_FILE"
else
  COMPOSE_FILE="$LEGACY_COMPOSE_FILE"
fi

echo "[deploy] dir=$APP_DIR branch=$BRANCH"
cd "$APP_DIR"

if [ -z "$DEPLOY_ENV_FILE" ]; then
  if [ -f "$APP_DIR/.env.server" ]; then
    DEPLOY_ENV_FILE="$APP_DIR/.env.server"
  elif [ -f "$APP_DIR/.env" ]; then
    DEPLOY_ENV_FILE="$APP_DIR/.env"
  else
    echo "[deploy] ERROR: no se encontró archivo de entorno (.env.server o .env)."
    exit 1
  fi
fi

if [ ! -f "$DEPLOY_ENV_FILE" ]; then
  echo "[deploy] ERROR: env file no existe: $DEPLOY_ENV_FILE"
  exit 1
fi
echo "[deploy] env_file=$DEPLOY_ENV_FILE"

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
  git config --global --add safe.directory "$APP_DIR" || true
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
    -e "runner/" \
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
ENV_FILE="$DEPLOY_ENV_FILE" "${COMPOSE_BIN[@]}" --env-file "$DEPLOY_ENV_FILE" --project-directory "$APP_DIR" -f "$COMPOSE_FILE" up -d --build

echo "[deploy] health..."
for i in {1..60}; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[deploy] OK"
    exit 0
  fi
  sleep 2
done

echo "[deploy] ERROR: healthcheck falló: $HEALTH_URL"
ENV_FILE="$DEPLOY_ENV_FILE" "${COMPOSE_BIN[@]}" --env-file "$DEPLOY_ENV_FILE" --project-directory "$APP_DIR" -f "$COMPOSE_FILE" ps || true
ENV_FILE="$DEPLOY_ENV_FILE" "${COMPOSE_BIN[@]}" --env-file "$DEPLOY_ENV_FILE" --project-directory "$APP_DIR" -f "$COMPOSE_FILE" logs --tail=120 api || true
exit 1
