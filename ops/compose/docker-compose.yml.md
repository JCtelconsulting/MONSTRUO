version: "3.9"

volumes:
  monstruo_pgdata:

services:
  db:
    image: postgres:16
    container_name: monstruo-postgres
    environment:
      POSTGRES_DB: monstruo
      POSTGRES_USER: monstruo
      POSTGRES_PASSWORD: monstruo
    ports:
      - "5432:5432"
    volumes:
      - monstruo_pgdata:/var/lib/postgresql/data
    restart: unless-stopped

  android-1:
    image: budtmo/docker-android:emulator_13.0
    container_name: monstruo-bancos-01
    privileged: true
    devices:
      - "/dev/kvm"
    ports:
      - "6080:6080" # Web UI (noVNC)
      - "5555:5555" # ADB
    environment:
      - DEVICE=Samsung Galaxy S10
      - EMULATOR_CPUS=4
      - EMULATOR_MEMORY=4096
      - WEB_VNC=true
      - SCREEN_WIDTH=1280
      - SCREEN_HEIGHT=720
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    container_name: monstruo-app-prod
    ports:
      - "9000:9000"
    environment:
      - PORT=9000
      - DB_URL=postgresql://monstruo:monstruo@db:5432/monstruo
      # En PROD define SECRET_KEY en el .env del servidor. En DEV usa el default inseguro.
      - SECRET_KEY=${SECRET_KEY:-CAMBIAME_ESTO_ES_INSEGURO_F8A9}
      # Cookies: para SSO entre subdominios (login.telconsulting.cl -> erp.telconsulting.cl)
      # En dev/local deja estas variables vacías.
      - COOKIE_DOMAIN=${COOKIE_DOMAIN:-}
      - COOKIE_SECURE=${COOKIE_SECURE:-0}
      - LAUDUS_BASE_URL=${LAUDUS_BASE_URL:-https://api.laudus.cl}
      - LAUDUS_USERNAME=${LAUDUS_USERNAME:-}
      - LAUDUS_PASSWORD=${LAUDUS_PASSWORD:-}
      - LAUDUS_COMPANY_VAT_ID=${LAUDUS_COMPANY_VAT_ID:-}
    volumes:
      - ./code:/app
    depends_on:
      - db
    restart: unless-stopped
