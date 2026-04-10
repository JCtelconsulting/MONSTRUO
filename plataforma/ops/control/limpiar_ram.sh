#!/bin/bash
# limpiar_ram.sh
set -euo pipefail

run_sudo() {
    if [ -n "${SUDO_PASS:-}" ]; then
        printf '%s\n' "$SUDO_PASS" | sudo -S "$@"
    else
        sudo "$@"
    fi
}

echo "Limpiando caches de memoria en WSL..."
run_sudo sysctl -w vm.drop_caches=3

echo "Memoria despues de la limpieza:"
free -h
sleep 3
