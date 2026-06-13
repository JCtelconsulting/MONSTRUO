FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Deps de sistema: libpq (Postgres), build-essential (compilar wheels),
# curl (healthcheck), ffmpeg/libsm6/libxext6 (Pillow / pillow-heif / imagenes y video).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY terreneitor/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Directorios de datos (los volumenes del compose los persisten en runtime)
RUN mkdir -p /app/data/files /app/data/db /app/data/reportes /app/data/locks /app/logs

# Usuario no-root (UID/GID parametrizable para coincidir con los bind-mounts del host)
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} appuser \
    && useradd -m -u ${APP_UID} -g ${APP_GID} appuser \
    && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:8005/health || exit 1

EXPOSE 8005

CMD ["uvicorn", "terreneitor.backend.main:app", "--host", "0.0.0.0", "--port", "8005"]
