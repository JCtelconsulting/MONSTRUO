FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY fundacion/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/


# Crear usuario no-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:9006/health || exit 1

CMD ["uvicorn", "fundacion.backend.main:app", "--host", "0.0.0.0", "--port", "9006"]
