#!/bin/bash
# control_terreneitor.sh

containers=("terreneitor_ai" "terreneitor_app" "terreneitor_labelbox")
any_running=false

for c in "${containers[@]}"; do
    if [ "$(docker ps -q -f name=$c)" ]; then
        any_running=true
        break
    fi
done

if [ "$any_running" = true ]; then
    echo "Apagando Terreneitor..."
    docker stop "${containers[@]}"
    echo "TERRENEITOR: OFF"
else
    echo "Encendiendo Terreneitor..."
    docker start "${containers[@]}"
    echo "TERRENEITOR: ON"
fi
sleep 2
