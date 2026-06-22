FROM python:3.12-slim

# Dependências de sistema: OCR (item 9) e renderização de PDF.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-por poppler-utils curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir pytesseract pdf2image ofxparse

COPY . .

ENV APP_DB_PATH=/app/data/app.db \
    OLLAMA_BASE_URL=http://ollama:11434 \
    OLLAMA_MODEL=llama3.2

EXPOSE 8501
ENTRYPOINT ["/app/docker-entrypoint.sh"]
