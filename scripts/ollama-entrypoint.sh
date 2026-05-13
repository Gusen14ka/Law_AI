#!/bin/bash
# Запускаем Ollama сервер в фоне
ollama serve &
OLLAMA_PID=$!

echo "[ollama-entrypoint] Server starting (PID $OLLAMA_PID)..."

# Ждём пока сервер поднимется
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "[ollama-entrypoint] Server is ready."
        break
    fi
    echo "[ollama-entrypoint] Waiting for server... ($i/30)"
    sleep 2
done

# Проверяем наличие модели
MODEL="${OLLAMA_MODEL:-mistral-nemo:12b}"
echo "[ollama-entrypoint] Checking model: $MODEL"

if ollama list | grep -q "${MODEL%%:*}"; then
    echo "[ollama-entrypoint] Model '$MODEL' already downloaded. Ready."
else
    echo "[ollama-entrypoint] Model '$MODEL' not found. Downloading..."
    echo "[ollama-entrypoint] This may take 10-20 minutes on first run."
    ollama pull "$MODEL"
    echo "[ollama-entrypoint] Model downloaded successfully."
fi

# Держим контейнер живым (ждём завершения сервера)
wait $OLLAMA_PID
