FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY crm/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/


# Crear usuario no-root (UID/GID parametrizable para coincidir con bind mounts del host)
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} appuser \
    && useradd -m -u ${APP_UID} -g ${APP_GID} appuser \
    && chown -R appuser:appuser /app
USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:9008/health || exit 1

CMD ["uvicorn", "crm.backend.main:app", "--host", "0.0.0.0", "--port", "9008"]
