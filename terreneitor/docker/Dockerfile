# ==========================================
# STAGE 1: Builder (Compilacion)
# ==========================================
FROM python:3.11-slim as builder

WORKDIR /app

# Variables para optimizar pip
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instalar dependencias de sistema para COMPILAR (gcc, libpq, etc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear Wheels de dependencias (cacheable)
# NOTA: Contexto de build debe ser la raiz del proyecto
COPY backend/requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


# ==========================================
# STAGE 2: Runner (Ejecucion)
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# Variables de entorno runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Instalar dependencias RUNTIME minimas (sin gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Copiar wheels del builder e instalar
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

RUN pip install --no-cache-dir /wheels/*

# Copiar codigo fuente
# NOTA: Regresamos a 'backend' (source) a '/app/backend' (container)
COPY ./backend /app/backend
COPY ./frontend /app/frontend

# Directorios de datos (volumenes)
RUN mkdir -p /app/data/files /app/data/db /app/data/logs /app/data/locks

# Usuario no-root para seguridad
RUN useradd -m -u 1000 runner && \
    chown -R runner:runner /app
USER runner

# Puerto
EXPOSE 8000

# Comando de inicio usando modulo
CMD ["python", "-m", "backend.core.cerebro"]
