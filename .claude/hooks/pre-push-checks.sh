#!/usr/bin/env bash
# Hook PreToolUse para Bash con matcher 'git push':
#   1. Detecta si el comando es realmente un git push (no `git push --help`,
#      no `git pushd`, etc).
#   2. Lee el rango de commits que se va a pushear (origin/<branch>..HEAD).
#   3. Si no hay commits nuevos, deja pasar (push vacío, no hay nada que revisar).
#   4. Llama al subagente code-reviewer SIEMPRE.
#   5. Si los cambios tocan DDL (db.py, migrations/, *.sql), llama también
#      a migration-tester.
#   6. Si alguno reporta 🔴 BLOQUEANTE, retorna exit 2 (bloquea el push) y
#      muestra el reporte por stderr para que Claude lo procese.
#
# Recibe por stdin un JSON del evento PreToolUse:
#   {
#     "tool_name": "Bash",
#     "tool_input": { "command": "git push origin dev" }
#   }
#
# Para que esto FUNCIONE como bloqueo de verdad, el hook debe imprimir
# instrucciones al agente principal por stderr y retornar exit 2.
# Ver: claude.com/docs hooks → "exit codes".

set -euo pipefail

REPO_ROOT="/srv/monstruo_dev"
LOG_FILE="$REPO_ROOT/.claude/hooks/pre-push.log"

ts=$(date '+%Y-%m-%d %H:%M:%S')

# 1. Leer evento JSON
event_json=$(cat)
cmd=$(echo "$event_json" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("command", ""))
except Exception:
    pass
' 2>/dev/null || echo "")

# 2. Filtrar: solo nos interesa "git push" real (no git push --help, no
#    git pushd, etc.). Hacemos un match estricto: el comando empieza con
#    "git push" seguido de espacio o final, no "git push-" o "git pushd".
if ! echo "$cmd" | grep -qE '^[[:space:]]*git[[:space:]]+push([[:space:]]|$)'; then
    # No es un git push real, no hacemos nada.
    exit 0
fi

# Excluir flags que NO ejecutan el push real
case "$cmd" in
    *"--help"*|*"-h "*|*"--dry-run"*)
        exit 0
        ;;
esac

cd "$REPO_ROOT"

# 3. Determinar el rango de commits que se va a pushear
branch=$(git rev-parse --abbrev-ref HEAD)
upstream="origin/${branch}"

# Si no hay upstream (primer push de un branch nuevo), no podemos comparar.
# Dejamos pasar — el push subsiguiente sí tendrá upstream.
if ! git rev-parse --verify "$upstream" >/dev/null 2>&1; then
    echo "[$ts] sin upstream para $branch, hook se salta" >> "$LOG_FILE"
    exit 0
fi

commits_ahead=$(git rev-list --count "${upstream}..HEAD" 2>/dev/null || echo "0")
if [[ "$commits_ahead" == "0" ]]; then
    echo "[$ts] sin commits nuevos vs $upstream, hook se salta" >> "$LOG_FILE"
    exit 0
fi

echo "[$ts] pre-push: $commits_ahead commits en ${upstream}..HEAD" >> "$LOG_FILE"

# 4. Detectar si los cambios tocan DDL
ddl_files=$(git diff "${upstream}..HEAD" --name-only 2>/dev/null \
    | grep -E '(plataforma/core/db\.py|migrations/.*\.sql|\.sql$)' || true)

run_migration_tester="false"
if [[ -n "$ddl_files" ]]; then
    run_migration_tester="true"
    echo "[$ts] cambios DDL detectados:" >> "$LOG_FILE"
    echo "$ddl_files" | sed 's/^/  /' >> "$LOG_FILE"
fi

# 5. Imprimir instrucciones al agente principal vía stderr.
#
# El agente principal (Claude) recibe este texto como contexto adicional
# antes de ejecutar el comando bloqueado. Le pedimos que invoque los
# subagentes y, según resultado, decida si pushear o no.
#
# Exit 2 = bloqueante con feedback en stderr. Claude lee stderr y actúa.

cat <<EOF >&2
═══════════════════════════════════════════════════════════════════
PRE-PUSH CHECKS — ${commits_ahead} commit(s) en ${upstream}..HEAD
═══════════════════════════════════════════════════════════════════

ANTES de ejecutar este push, debés invocar los siguientes subagentes
y procesar sus reportes:

1. **code-reviewer** (SIEMPRE)
   Invocá la tool Agent con:
     subagent_type: "code-reviewer"
     prompt: "Revisá el diff entre ${upstream} y HEAD del repo
              ${REPO_ROOT}. Comando: cd ${REPO_ROOT} && git diff
              ${upstream}..HEAD --stat para listar archivos, después
              git diff ${upstream}..HEAD para el diff completo.
              Reportá hallazgos."

EOF

if [[ "$run_migration_tester" == "true" ]]; then
    cat <<EOF >&2
2. **migration-tester** (cambios DDL detectados)
   Invocá la tool Agent con:
     subagent_type: "migration-tester"
     prompt: "Validá las migraciones nuevas en ${upstream}..HEAD
              del repo ${REPO_ROOT} contra la DB de PROD
              (192.168.60.5, container monstruo-db).
              Archivos DDL afectados:
$(echo "$ddl_files" | sed 's/^/                /')
              Seguí el procedimiento de pg_dump + sandbox y reportá."

EOF
else
    cat <<EOF >&2
2. **migration-tester** (skipped — no hay cambios DDL)

EOF
fi

cat <<EOF >&2
PROCESAMIENTO DE REPORTES:

- Si CUALQUIERA reporta 🔴 BLOQUEANTE:
  • NO ejecutes el push.
  • Mostrale al usuario el reporte completo.
  • Sugerí los fix concretos por archivo:línea.
  • Esperá instrucciones explícitas del usuario antes de pushear.

- Si solo hay 🟡 IMPORTANTE o 🟢 SUGERENCIA:
  • Mostrale al usuario el reporte como aviso.
  • Procedé con el push.

- Si todo está limpio:
  • Procedé con el push, mencionando "checks PASS".

Una vez procesados los reportes y decidida la acción, ejecutá el
git push original (o no) según corresponda.

═══════════════════════════════════════════════════════════════════
EOF

# Exit 2 = bloquear el comando original y devolver el contexto al agente
# para que tome acción. El agente reintentará después de invocar los
# subagentes y procesar los reportes.
exit 2
