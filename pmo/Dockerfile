FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pmo/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

CMD ["uvicorn", "pmo.main:app", "--host", "0.0.0.0", "--port", "8000"]
