#!/bin/bash
# control_monstruo.sh
SUDO_PASS="Apstref.8"

is_running() {
    systemctl is-active --quiet monstruo-api
}

if is_running; then
    echo "Apagando Monstruo (API + DB)..."
    echo $SUDO_PASS | sudo -S systemctl stop monstruo-api
    docker stop monstruo-postgres ws-scrcpy
    echo "MONSTRUO: OFF"
else
    echo "Encendiendo Monstruo (API + DB)..."
    echo $SUDO_PASS | sudo -S systemctl start monstruo-api
    docker start monstruo-postgres ws-scrcpy
    echo "MONSTRUO: ON"
fi
sleep 2
