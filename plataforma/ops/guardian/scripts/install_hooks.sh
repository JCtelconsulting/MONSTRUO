#!/bin/bash
set -euo pipefail
# ops/guardian/scripts/install_hooks.sh
# Instala el pre-commit hook para asegurar el orden del repo.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HOOK_PATH="$PROJECT_ROOT/.git/hooks/pre-commit"
GUARDIAN_SCRIPT="$PROJECT_ROOT/ops/guardian/scripts/orden_guardian.py"

echo "--- Instalando Guardian Git Hook ---"

if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "ERROR: No se encontro .git en $PROJECT_ROOT"
    exit 1
fi

if [ ! -f "$GUARDIAN_SCRIPT" ]; then
    echo "ERROR: No se encuentra orden_guardian.py en $GUARDIAN_SCRIPT"
    exit 1
fi

cat <<EOF > "$HOOK_PATH"
#!/bin/bash
# Monstruo Guardian Pre-Commit Hook
# Creado automaticamente por install_hooks.sh

echo "[guardian] Validando estructura..."

# Validar solo lo que esta en stage (cached)
if git diff --cached | python3 "$GUARDIAN_SCRIPT" --check-patch -; then
    echo "[guardian] Estructura aprobada."
    exit 0
else
    echo "[guardian] BLOQUEADO: Tu commit viola las reglas de estructura (EPIC 01)."
    echo "   Revisa la regla violada o contacta al Arquitecto."
    exit 1
fi
EOF

chmod +x "$HOOK_PATH"
echo "Hook instalado en $HOOK_PATH"
echo "Prueba: Intenta comitear algo fuera de lugar y veras el error."
