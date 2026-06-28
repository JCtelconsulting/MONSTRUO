#!/usr/bin/env bash
# run-tests.sh — corre los tests de los módulos indicados dentro de sus containers DEV.
#
# Por qué así: los containers de runtime no traen pytest (son de producción), pero sí
# tienen todas las deps de la app + acceso a la DB dev. Instalamos pytest on-demand
# (efímero) y corremos la suite del módulo. Pensado para correr ANTES de pasar a prod.
#
# Uso:
#   ./run-tests.sh                      # módulos core (gateway ticketera gta terreneitor)
#   ./run-tests.sh ticketera gateway    # solo esos
#   FAST=1 ./run-tests.sh ticketera     # solo unitarios (-m "not integration")
#
# Sale con código !=0 si algún módulo tiene tests fallando (para usar en gates).

set -u

MODULES=("$@")
if [ ${#MODULES[@]} -eq 0 ]; then
  MODULES=(gateway ticketera gta terreneitor)
fi

# terreneitor: los e2e necesitan navegador (Playwright). Por defecto corremos solo unit.
declare -A TESTPATH=(
  [terreneitor]="terreneitor/tests/unit"
)

MARK=""
[ "${FAST:-0}" = "1" ] && MARK="-m 'not integration'"

OVERALL=0
SUMMARY=""
for m in "${MODULES[@]}"; do
  c="monstruo-dev-${m}"
  path="${TESTPATH[$m]:-${m}/tests}"
  if ! docker inspect "$c" >/dev/null 2>&1; then
    echo "=== ${m}: container ${c} no existe, salto ==="
    SUMMARY="${SUMMARY}\n  ${m}: SKIP (sin container)"
    continue
  fi
  echo "============================================================"
  echo "=== ${m}  (pytest ${path} ${MARK})"
  echo "============================================================"
  out=$(docker exec "$c" sh -c \
    "python -m pip install -q pytest pytest-asyncio 2>/dev/null; cd /app && python -m pytest ${path} ${MARK} -q --no-header 2>&1")
  echo "$out" | tail -6
  line=$(echo "$out" | grep -E "passed|failed|error" | tail -1)
  if echo "$line" | grep -qE "failed|error"; then
    OVERALL=1
    SUMMARY="${SUMMARY}\n  ${m}: ❌ ${line}"
  else
    SUMMARY="${SUMMARY}\n  ${m}: ✅ ${line}"
  fi
done

echo
echo "============================================================"
echo "RESUMEN"
echo -e "$SUMMARY"
echo "============================================================"
exit $OVERALL
