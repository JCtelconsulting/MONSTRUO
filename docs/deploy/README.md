# Deploy profesional (PC ⇄ GitHub ⇄ Servidor + Nginx)

Objetivo:
- Código vive en GitHub.
- Tu PC hace cambios y sube a `main` (vía PR/merge).
- El servidor se actualiza solo con GitHub Actions.
- Nginx (proxy inverso) enruta por dominios a la VM de la app.

## Topología sugerida (Telconsulting)
- Proxy Nginx: `192.168.60.6`
- Monstruo (app + postgres via docker compose): `192.168.60.5`
- Ruta de instalación en la VM app: `/srv/monstruo`

## 1) Preparación en la VM de la app (192.168.60.5)

### Requisitos
- `git`
- `docker` + `docker compose`

### Clonar repo
```bash
sudo mkdir -p /srv/monstruo
sudo chown -R $USER:$USER /srv/monstruo
git clone git@github.com:JCtelconsulting/MONSTRUO.git /srv/monstruo
cd /srv/monstruo
```

### Crear `.env` del servidor (NO va a git)
Usar plantilla de servidor y completar secretos:

```bash
cd /srv/monstruo
cp .env.server.example .env.server
```

Claves recomendadas para PROD:
- `SECRET_KEY=<largo/aleatorio>`
- `COOKIE_DOMAIN=.telconsulting.cl`
- `COOKIE_SECURE=1`

### Levantar
```bash
cd /srv/monstruo
docker compose --env-file .env.server up -d --build
curl -fsS http://127.0.0.1:9000/health
```

## 2) Nginx (proxy) en 192.168.60.6

Cuando tengas DNS:
- `login.telconsulting.cl` → `192.168.60.6`
- `erp.telconsulting.cl` → `192.168.60.6`

Usa las plantillas:
- `docs/deploy/nginx/login.telconsulting.cl.conf`
- `docs/deploy/nginx/erp.telconsulting.cl.conf`

Luego habilita TLS (ej con certbot) y recarga Nginx.

## 3) GitHub Actions (auto deploy)

Workflow: `.github/workflows/deploy.yml`

Este flujo corre tests en GitHub y despliega desde un runner self-hosted en la VM de la app.
El deploy está configurado por rama:
- `main` -> `DEPLOY_ENV_FILE=/srv/monstruo/.env.server`
- `dev` -> `DEPLOY_ENV_FILE=/srv/monstruo_dev/.env.server.dev`

Metodo correcto (evita conflicto "container name already in use"):
- Diferenciar `project` de Docker Compose vs `stack` (nombre visible del contenedor).
- `project` debe ser estable en el tiempo por ambiente:
  - `main`: `monstruo`
  - `dev`: `monstruo_dev`
- `stack` puede mantener guiones para nombres humanos:
  - `main`: `monstruo`
  - `dev`: `monstruo-dev`
- No alternar `monstruo-dev` y `monstruo_dev` en `project`; eso rompe ownership de Compose aunque el `container_name` sea el mismo.

Pasos:
- En GitHub → Settings → Actions → Runners, agrega un runner self-hosted para este repo y ejecútalo en `192.168.60.5` (puedes usar `/srv/monstruo_dev/runner`).
- Asegura que el usuario del runner tenga acceso a Docker (`docker` group).
- En GitHub → Settings → Environments, crea el entorno `production` y configura "Required reviewers" para aprobar el deploy.

## 4) Flujo de trabajo recomendado
- PC: branch → PR → merge a `main`
- GitHub Actions: despliega automático en `192.168.60.5`
- Nginx: solo enruta por dominios (no se toca el código)

## Nota: compatibilidad PC/servidor
- En PC/dev usa `.env.local` con `COOKIE_DOMAIN=` y `COOKIE_SECURE=0`.
- En servidor/prod usa `.env.server` con `COOKIE_DOMAIN=.telconsulting.cl` y `COOKIE_SECURE=1` para compartir sesión entre subdominios.

## Nota: flujo seguro de variables por entorno
- No subir `.env*` al repo (ya ignorado por `.gitignore`).
- Plantillas versionadas:
  - `.env.local.example`
  - `.env.server.example`
  - `.env.example` (base genérica)
- Local recomendado:

```bash
cd /srv/monstruo
cp .env.local.example .env.local
docker compose --env-file .env.local up -d
```

- Servidor recomendado:

```bash
cd /srv/monstruo
cp .env.server.example .env.server
docker compose --env-file .env.server up -d --build
```

Prueba de CI/CD: 2026-02-08.

## 6) Entorno DEV paralelo (sin abrir nuevos puertos)

- Crea archivo de entorno DEV en la VM app:

```bash
cd /srv/monstruo
cp .env.server.dev.example .env.server.dev
```

- El workflow deploy usa:
  - `main` -> project `monstruo`, stack `monstruo` (`:9000`)
  - `dev` -> project `monstruo_dev`, stack `monstruo-dev` (`:9001`)

- En el proxy Nginx (443), selecciona entorno por cookie:
  - `https://<dominio>/__env/dev` -> enruta a `:9001`
  - `https://<dominio>/__env/prod` -> enruta a `:9000`

## 5) Ver versión desplegada

La API expone `GET /version` con metadata del deploy:

```bash
curl -fsS http://127.0.0.1:9000/version
```

Respuesta esperada:
- `git_sha`: commit desplegado
- `branch`: rama usada en deploy
- `build_time`: timestamp UTC de construcción/despliegue

### Relación con GitHub
- En GitHub Actions puedes ver el SHA del run (`actions/checkout`).
- Debe coincidir con `git_sha` del endpoint `/version` para confirmar que el server está en esa versión.
