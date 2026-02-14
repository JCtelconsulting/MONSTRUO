#!/bin/bash
# Script de ejecución de suite E2E Ticketera en DEV
# Captura de evidencia automática
set -uo pipefail

export MONSTRUO_TEST_BASE_URL="http://127.0.0.1:9001"
export MONSTRUO_TEST_USER="juan.lopez@telconsulting.cl"
export MONSTRUO_TEST_PASSWORD="Monstruo2024!"

OUTPUT_FILE="docs/playbooks/e2e_ticketera_dev_validacion.md"

{
    echo "# Validación E2E Ticketera - DEV"
    echo "**Fecha:** $(date)"
    echo "**Commit:** $(git rev-parse --short HEAD)"
    echo ""
    echo "## Ejecución de Pruebas"
    echo ""

    echo "### 1. verify_hardening.py"
    echo "\`\`\`"
    if python3 tests/verify_hardening.py; then
        echo "[PASS] verify_hardening.py"
    else
        echo "[FAIL] verify_hardening.py"
        exit 1
    fi
    echo "\`\`\`"
    echo ""

    echo "### 2. verify_hardening.py --check-api"
    echo "\`\`\`"
    if python3 tests/verify_hardening.py --check-api; then
        echo "[PASS] verify_hardening.py --check-api"
    else
        echo "[FAIL] verify_hardening.py --check-api"
        exit 1
    fi
    echo "\`\`\`"
    echo ""

    echo "### 3. e2e_api_full.py"
    echo "\`\`\`"
    if python3 tests/e2e_api_full.py; then
        echo "[PASS] e2e_api_full.py"
    else
        echo "[FAIL] e2e_api_full.py"
        exit 1
    fi
    echo "\`\`\`"
    echo ""

    echo "### 4. e2e_ticketera.py (Incoming Match)"
    echo "\`\`\`"
    if python3 tests/e2e_ticketera.py; then
        echo "[PASS] e2e_ticketera.py"
    else
        echo "[FAIL] e2e_ticketera.py"
        exit 1
    fi
    echo "\`\`\`"

} | tee "$OUTPUT_FILE"
