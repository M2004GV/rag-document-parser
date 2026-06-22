#!/usr/bin/env bash
set -e

OLLAMA_URL="${OLLAMA_BASE_URL:-http://ollama:11434}"
MODEL="${OLLAMA_MODEL:-llama3.2}"

echo "Aguardando o Ollama em ${OLLAMA_URL}..."
until curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; do
    sleep 2
done

echo "Garantindo o modelo ${MODEL}..."
if ! curl -sf "${OLLAMA_URL}/api/tags" | grep -q "\"${MODEL}\""; then
    curl -sf "${OLLAMA_URL}/api/pull" -d "{\"name\": \"${MODEL}\"}" >/dev/null || true
fi

echo "Iniciando Streamlit..."
exec streamlit run invoice-extraction.py \
    --server.address=0.0.0.0 --server.port=8501 --server.headless=true
