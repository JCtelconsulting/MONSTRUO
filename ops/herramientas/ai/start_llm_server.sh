#!/bin/bash
# start_llm_server.sh - Starts Ollama server

echo "STARTING OLLAMA SERVER"

# 1. Check if running
if pgrep -x "ollama" > /dev/null; then
    echo "Ollama is already running."
else
    echo "Starting Ollama..."
    nohup ollama serve > /srv/monstruo/data/ollama.log 2>&1 &
    sleep 5
fi

# 2. Check connectivity
curl -s http://127.0.0.1:11434/v1/models > /dev/null
if [ $? -eq 0 ]; then
    echo "Ollama is UP and listening on 11434"
else
    echo "ERROR: Ollama failed to start or is not reachable."
    exit 1
fi

echo "Recommended Env Vars for Monstruo:"
echo "export ULTRON_LLM_ENABLED=1"
echo "export ULTRON_LLM_BASE_URL=\"http://127.0.0.1:11434/v1\""
echo "export ULTRON_LLM_MODEL=\"telconsulting-rapido:latest\""
