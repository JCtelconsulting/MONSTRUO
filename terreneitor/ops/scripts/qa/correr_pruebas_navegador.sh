#!/usr/bin/env bash
# Corre las pruebas de navegador (Playwright) contra el entorno DEV usando la
# imagen oficial de Playwright en Docker (sin instalar nada en el host).
# Uso: bash ops/scripts/qa/correr_pruebas_navegador.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
IMG="mcr.microsoft.com/playwright/python:v1.49.0-jammy"

# La imagen trae los navegadores; el paquete python de Playwright se instala en
# runtime FIJADO a la version de la imagen (1.49.0) para que el chromium calce.
docker run --rm --network host \
  -v "${REPO}:/work" -w /work \
  -e BASE_URL="${BASE_URL:-https://portal.telconsulting.cl/dev}" \
  -e QA_EMAIL="${QA_EMAIL:-qa.dev@telconsulting.cl}" \
  -e QA_PASS="${QA_PASS:-QaDev2026!}" \
  -e SHOT_DIR="/work/e2e/shots" \
  "${IMG}" bash -lc 'pip install -q --break-system-packages "playwright==1.49.0" >/dev/null 2>&1; python3 e2e/test_dev_navegador.py'
