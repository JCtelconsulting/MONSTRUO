#!/usr/bin/env bash
# Wrapper para el MCP server de Postgres. Resuelve la IP actual del
# container monstruo-dev-db en runtime (puede cambiar al recrear el
# container) y arranca el server con la connection string correcta.
#
# Lee la contraseña de la env file del repo (no se hardcodea acá ni en
# .mcp.json).

set -euo pipefail

ENV_FILE="/srv/monstruo_dev/plataforma/ops/env/.env.server.dev"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: env file no encontrado: $ENV_FILE" >&2
    exit 1
fi

# Extraer credenciales del env file
PGUSER=$(grep -E "^POSTGRES_USER=" "$ENV_FILE" | cut -d= -f2-)
PGPASSWORD=$(grep -E "^POSTGRES_PASSWORD=" "$ENV_FILE" | cut -d= -f2-)
PGDATABASE=$(grep -E "^POSTGRES_DB=" "$ENV_FILE" | cut -d= -f2-)

# Resolver IP del container actual
PGHOST=$(docker inspect monstruo-dev-db \
    --format '{{range $k, $v := .NetworkSettings.Networks}}{{$v.IPAddress}}{{end}}' 2>/dev/null)

if [[ -z "$PGHOST" ]]; then
    echo "ERROR: container monstruo-dev-db no encontrado o sin IP" >&2
    exit 1
fi

# Connection string para el MCP server
CONN_STRING="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:5432/${PGDATABASE}"

# Lanzar el MCP server de Postgres (oficial, npx-on-demand)
exec npx -y @modelcontextprotocol/server-postgres "$CONN_STRING"
