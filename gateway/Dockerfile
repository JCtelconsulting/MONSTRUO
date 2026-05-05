FROM python:3.12-slim

WORKDIR /app

# Dependencias de sistema básicas
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalación de dependencias de Python
COPY gateway/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el repositorio pero el PYTHONPATH se ajustará por servicio
COPY . /app/

# El CMD se define en el docker-compose por cada servicio

# Crear usuario no-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:9001/health || exit 1

CMD ["uvicorn", "gateway.backend.main:app", "--host", "0.0.0.0", "--port", "9001"]
