FROM python:3.12-slim


WORKDIR /app

# Dependencias de sistema básicas
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalación de dependencias de Python
COPY ticketera/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el repositorio pero el PYTHONPATH se ajustará por servicio
COPY . /app/

# El CMD se define en el docker-compose por cada servicio
CMD ["uvicorn", "ticketera.backend.main:app", "--host", "0.0.0.0", "--port", "9005"]
