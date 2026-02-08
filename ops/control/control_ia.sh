#!/bin/bash
# control_ia.sh

model="qwen2.5-coder:7b"

if ollama ps | grep -q "$model"; then
    echo "Apagando IA (Modelo $model)..."
    ollama stop "$model"
    echo "IA: OFF"
else
    echo "Encendiendo IA (Modelo $model)..."
    # Iniciamos en background para no bloquear
    nohup ollama run "$model" </dev/null >/dev/null 2>&1 &
    echo "IA: ON (Cargando...)"
fi
sleep 2
