#!/bin/bash
# ops/guardian/scripts/install_hooks.sh
# Instala el pre-commit hook para asegurar el orden del repo.

HOOK_PATH=".git/hooks/pre-commit"
GUARDIAN_SCRIPT="/srv/monstruo/ops/guardian/scripts/orden_guardian.py"

echo "--- Instalando Guardian Git Hook ---"

if [ ! -f "$GUARDIAN_SCRIPT" ]; then
    echo "ERROR: No se encuentra orden_guardian.py en $GUARDIAN_SCRIPT"
    exit 1
fi

cat <<EOF > "$HOOK_PATH"
#!/bin/bash
# Monstruo Guardian Pre-Commit Hook
# Creado automaticamente por install_hooks.sh

echo "🔍 Guardian del Orden: Validando cambios..."

# Validar solo lo que esta en stage (cached)
if git diff --cached | python3 "$GUARDIAN_SCRIPT" --check-patch -; then
    echo "✅ Estructura Aprobada."
    exit 0
else
    echo "❌ BLOQUEADO: Tu commit viola las reglas de estructura (EPIC 01)."
    echo "   Consulta docs/estructura_repo.json o contacta al Arquitecto."
    exit 1
fi
EOF

chmod +x "$HOOK_PATH"
echo "✅ Hook instalado en $HOOK_PATH"
echo "Prueba: Intenta comitear algo fuera de lugar y veras el error."
