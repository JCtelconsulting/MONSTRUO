#!/bin/bash
# control_monstruo.sh
set -euo pipefail

run_sudo() {
    if [ -n "${SUDO_PASS:-}" ]; then
        printf '%s\n' "$SUDO_PASS" | sudo -S "$@"
    else
        sudo "$@"
    fi
}

is_running() {
    systemctl is-active --quiet monstruo-api
}

if is_running; then
    echo "Apagando Monstruo (API + DB)..."
    run_sudo systemctl stop monstruo-api
    docker stop monstruo-postgres ws-scrcpy
    echo "MONSTRUO: OFF"
else
    echo "Encendiendo Monstruo (API + DB)..."
    run_sudo systemctl start monstruo-api
    docker start monstruo-postgres ws-scrcpy
    echo "MONSTRUO: ON"
fi
sleep 2
