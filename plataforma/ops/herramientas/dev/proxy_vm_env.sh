#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SECRETS_FILE="${PROXY_VM_SECRETS_FILE:-$ROOT_DIR/.secrets/proxy_vm.env}"

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "No existe archivo de credenciales: $SECRETS_FILE" >&2
  echo "Usa: cp ops/herramientas/dev/proxy_vm.env.example .secrets/proxy_vm.env" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "$SECRETS_FILE"
set +a

if [[ "${1:-}" == "--exports" ]]; then
  printf "export PROXY_VM_HOST=%q\n" "${PROXY_VM_HOST:-}"
  printf "export PROXY_VM_USER=%q\n" "${PROXY_VM_USER:-}"
  printf "export PROXY_VM_SSH_PORT=%q\n" "${PROXY_VM_SSH_PORT:-22}"
  printf "export PROXY_VM_SUDO_PASS=%q\n" "${PROXY_VM_SUDO_PASS:-}"
  exit 0
fi

echo "Credenciales cargadas desde $SECRETS_FILE"
echo "Host: ${PROXY_VM_HOST:-unset} | User: ${PROXY_VM_USER:-unset} | Port: ${PROXY_VM_SSH_PORT:-22}"
