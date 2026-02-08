#!/bin/bash
# Script Maestro para Iniciar Entorno Local (Monstruo + Terreneitor)
# Autor: Antigravity
# Fecha: 2026-01-26

echo "=========================================="
echo "🚀 INICIANDO ENTORNO LOCAL DE TELCONSULTING"
echo "=========================================="
echo ""

# 0. Cargar credenciales para modo desatendido
if [ -f /srv/monstruo/.env ]; then
    set -o allexport
    source /srv/monstruo/.env
    set +o allexport
fi
: ${SUDO_PASS:="Apstref.8"} # Fallback

# 1. Monstruo (Systemd Service)
echo "[1/2] Iniciando MONSTRUO (Puerto 9000)..."
echo "$SUDO_PASS" | sudo -S systemctl restart monstruo-api

if systemctl is-active --quiet monstruo-api; then
    echo "✅ MONSTRUO: ONLINE"
else
    echo "❌ MONSTRUO: FALLA"
fi

echo ""

# 2. Terreneitor
echo "[2/2] Iniciando TERRENEITOR..."
if [ -d "/srv/terreneitor" ]; then
    cd /srv/terreneitor
    # Ejecutar en background y disown para que sobreviva si se cierra la terminal
    nohup ./start.sh > logs/terreneitor_launcher.log 2>&1 &
    echo "✅ TERRENEITOR: INICIADO (Background)"
else
    echo "⚠️  No se encontró /srv/terreneitor"
fi

# Pausa breve para asegurar init
sleep 2
