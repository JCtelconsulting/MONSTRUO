#!/bin/bash
# limpiar_ram.sh
SUDO_PASS="Apstref.8"

echo "Limpiando caches de memoria en WSL..."
echo $SUDO_PASS | sudo -S sysctl -w vm.drop_caches=3

echo "Memoria despues de la limpieza:"
free -h
sleep 3
