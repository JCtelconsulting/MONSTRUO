#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DEPLOY_PATH:-/srv/monstruo}"
BRANCH="${DEPLOY_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:9000/health}"
DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-}"
DEPLOY_COMPOSE_PROJECT="${DEPLOY_COMPOSE_PROJECT:-}"
DEPLOY_STACK_NAME="${DEPLOY_STACK_NAME:-}"

DEFAULT_COMPOSE_FILE="$APP_DIR/docker-compose.yaml"
LEGACY_COMPOSE_FILE="$APP_DIR/docs/deploy/docker-compose.yaml"
if [ -n "${COMPOSE_FILE:-}" ]; then
  COMPOSE_FILE="$COMPOSE_FILE"
elif [ -f "$DEFAULT_COMPOSE_FILE" ]; then
  COMPOSE_FILE="$DEFAULT_COMPOSE_FILE"
else
  COMPOSE_FILE="$LEGACY_COMPOSE_FILE"
fi


# Capture Origin URL from current (runner) workspace before switching context
REPO_URL="$(git remote get-url origin || echo '')"

echo "[deploy] dir=$APP_DIR branch=$BRANCH"

# Ensure target dir exists
if [ ! -d "$APP_DIR" ]; then
  echo "[deploy] Creating $APP_DIR..."
  mkdir -p "$APP_DIR"
fi

cd "$APP_DIR"

# Initialize git if missing
if [ ! -d ".git" ] && [ -n "$REPO_URL" ]; then
  echo "[deploy] Initializing git repo from $REPO_URL..."
  git init
  git remote add origin "$REPO_URL"
  git fetch origin "$BRANCH"
  git checkout -f "$BRANCH"
fi

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
if [ -n "$DEPLOY_COMPOSE_PROJECT" ]; then
  echo "[deploy] compose_project=$DEPLOY_COMPOSE_PROJECT"
fi
if [ -n "$DEPLOY_STACK_NAME" ]; then
  echo "[deploy] stack_name=$DEPLOY_STACK_NAME"
fi

if grep -Eq '^DB_URL=.*(localhost|127\.0\.0\.1|::1)' "$DEPLOY_ENV_FILE"; then
  DB_URL='postgresql://monstruo:monstruo@db:5432/monstruo'
  export DB_URL
  echo "[deploy] WARN: DB_URL local detectado en env. Se fuerza host docker: $DB_URL"
fi

APP_GIT_SHA="unknown"
APP_GIT_BRANCH="$BRANCH"
APP_BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

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

COMPOSE_ARGS=(--env-file "$DEPLOY_ENV_FILE" --project-directory "$APP_DIR" -f "$COMPOSE_FILE")
if [ -n "$DEPLOY_COMPOSE_PROJECT" ]; then
  COMPOSE_ARGS+=(-p "$DEPLOY_COMPOSE_PROJECT")
fi

if [ "$HAS_GIT_REPO" = "1" ]; then
  git config --global --add safe.directory "$APP_DIR" || true
  echo "[deploy] fetch..."
  git fetch origin "$BRANCH" --prune

  echo "[deploy] checkout/reset..."
  git checkout -q "$BRANCH"
  git reset --hard "origin/$BRANCH"
  APP_GIT_SHA="$(git rev-parse --short HEAD)"

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

echo "[deploy] version sha=$APP_GIT_SHA branch=$APP_GIT_BRANCH build_time=$APP_BUILD_TIME"
APP_GIT_SHA="$APP_GIT_SHA" APP_GIT_BRANCH="$APP_GIT_BRANCH" APP_BUILD_TIME="$APP_BUILD_TIME" ENV_FILE="$DEPLOY_ENV_FILE" STACK_NAME="$DEPLOY_STACK_NAME" "${COMPOSE_BIN[@]}" "${COMPOSE_ARGS[@]}" up -d --build

echo "[deploy] health..."
for i in {1..60}; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[deploy] OK"
    exit 0
  fi
  sleep 2
done

echo "[deploy] ERROR: healthcheck falló: $HEALTH_URL"
ENV_FILE="$DEPLOY_ENV_FILE" STACK_NAME="$DEPLOY_STACK_NAME" "${COMPOSE_BIN[@]}" "${COMPOSE_ARGS[@]}" ps || true
ENV_FILE="$DEPLOY_ENV_FILE" STACK_NAME="$DEPLOY_STACK_NAME" "${COMPOSE_BIN[@]}" "${COMPOSE_ARGS[@]}" logs --tail=120 api || true
exit 1
