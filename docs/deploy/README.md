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
Crear `/srv/monstruo/.env` basado en `.env.example` y setear secretos reales.

Claves recomendadas para PROD:
- `SECRET_KEY=<largo/aleatorio>`
- `COOKIE_DOMAIN=.telconsulting.cl`
- `COOKIE_SECURE=1`

### Levantar
```bash
cd /srv/monstruo
docker compose up -d --build
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

Pasos:
- En GitHub → Settings → Actions → Runners, agrega un runner self-hosted para este repo y ejecútalo en `192.168.60.5` (puedes usar `/srv/monstruo/runner`).
- Asegura que el usuario del runner tenga acceso a Docker (`docker` group).
- En GitHub → Settings → Environments, crea el entorno `production` y configura "Required reviewers" para aprobar el deploy.

## 4) Flujo de trabajo recomendado
- PC: branch → PR → merge a `main`
- GitHub Actions: despliega automático en `192.168.60.5`
- Nginx: solo enruta por dominios (no se toca el código)

## Nota: compatibilidad PC/servidor
- En PC/dev deja `COOKIE_DOMAIN` vacío y `COOKIE_SECURE=0`.
- En servidor/prod usa `COOKIE_DOMAIN=.telconsulting.cl` y `COOKIE_SECURE=1` para compartir sesión entre subdominios.
