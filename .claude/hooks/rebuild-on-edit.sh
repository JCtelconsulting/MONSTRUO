#!/usr/bin/env bash
# Hook PostToolUse: rebuildea automáticamente el container de la app cuya
# UI/backend fue editada. Evita el síntoma "no veo los cambios" tras editar
# código sin recordar hacer docker compose up -d --build.
#
# Recibe por stdin un JSON del evento PostToolUse con shape:
#   {
#     "tool_name": "Edit" | "Write",
#     "tool_input": { "file_path": "/abs/path/to/file" }
#   }
#
# Mapea el path → app afectada → container, y dispara rebuild en background
# para no bloquear la conversación. Loguea a .claude/hooks/rebuild.log.

set -euo pipefail

REPO_ROOT="/srv/monstruo_dev"
LOG_FILE="$REPO_ROOT/.claude/hooks/rebuild.log"
ENV_FILE="$REPO_ROOT/plataforma/ops/env/.env.server.dev"

# Lee evento JSON desde stdin
event_json=$(cat)

# Extrae el path editado (jq sería ideal pero usamos python por portabilidad)
file_path=$(echo "$event_json" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("file_path", ""))
except Exception:
    pass
' 2>/dev/null || echo "")

# Si no hay path o no es del repo, salir silencioso
if [[ -z "$file_path" || "$file_path" != "$REPO_ROOT"/* ]]; then
    exit 0
fi

# Path relativo al repo
rel="${file_path#$REPO_ROOT/}"

# Solo extensiones de runtime (Python/HTML/CSS/JS). Markdown/JSON/SQL/etc no
# disparan rebuild — son docs o requieren intervención manual.
case "$rel" in
    *.py|*.html|*.css|*.js)
        ;;
    *)
        exit 0
        ;;
esac

# Mapear primer segmento del path → container
app=$(echo "$rel" | cut -d/ -f1)
case "$app" in
    gateway|ticketera|gta|fundacion|crm|erp|bodega|pmo|ia|zabbix)
        container="$app"
        ;;
    plataforma)
        # plataforma/core/* es compartido — rebuildear gateway como mínimo.
        # Las demás apps lo recogerán al rebuildear cuando las toques.
        container="gateway"
        ;;
    *)
        # gta/ui/shared, .claude, plataforma/docs, etc — no rebuildea
        exit 0
        ;;
esac

# Calcular SHA actual del repo (puede no estar commiteado, no importa)
sha=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "dev")
ts=$(date '+%Y-%m-%d %H:%M:%S')

# Echo de feedback al usuario en stderr (Claude Code lo muestra)
echo "[hook rebuild] editado $rel → rebuildeando $container (sha=$sha, en background)" >&2

# Lanzar rebuild en background. No bloqueamos la respuesta del agente.
{
    echo "[$ts] rebuild $container (sha=$sha) por edición de $rel"
    cd "$REPO_ROOT"
    ASSET_VERSION="$sha" \
      APP_UID=$(id -u) APP_GID=$(id -g) \
      docker compose --env-file "$ENV_FILE" up -d --build "$container" 2>&1
    echo "[$(date '+%H:%M:%S')] rebuild $container terminado"
    echo "---"
} >> "$LOG_FILE" 2>&1 &

exit 0
