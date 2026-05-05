# Guía de Deploy

Cómo se despliega Monstruo: PC → GitHub → VM de aplicaciones, con Nginx como proxy inverso.

> Para detalle del proxy inverso ver [arquitectura/PROXY_INVERSO.md](../../arquitectura/PROXY_INVERSO.md). Para contrato canónico DEV/PROD ver [PROYECTO_CONTEXTO.md](../../PROYECTO_CONTEXTO.md).

## Topología

| Pieza | IP / Path | Rol |
|---|---|---|
| Proxy Nginx | `192.168.60.6` | Termina TLS y enruta por dominio a la VM de apps |
| VM apps PROD | `192.168.60.5` | `docker compose` con stack `monstruo`, ruta `/srv/monstruo` |
| VM apps DEV | `192.168.60.8` | `docker compose` con stack `monstruo-dev`, ruta `/srv/monstruo_dev` |

## Contrato canónico DEV/PROD

Validado por `plataforma/tests/ci_repo_guard.py`. Reglas no negociables:

| Variable | DEV | PROD |
|---|---|---|
| Branch | `dev` | `main` |
| `project` (compose) | `monstruo_dev` | `monstruo` |
| `STACK_NAME` (containers) | `monstruo-dev` | `monstruo` |
| `ENV_FILE` | `plataforma/ops/env/.env.server.dev` | `plataforma/ops/env/.env.server` |
| Gateway publica | `${GATEWAY_PORT:-9001}` | `9001` |
| Ticketera publica | `${TICKETERA_PORT:-9005}` | `9005` |
| Postgres | NUNCA publica `5432` al host | NUNCA publica `5432` al host |

> **Estado PROD** (verificado 2026-05-05): el proxy ya enruta a `9001/9005/9006`. Confirmar caso por caso que las apps en `192.168.60.5` escuchen en esos puertos y que `HEALTH_URL` en `.github/workflows/deploy.yml` apunte a `9001` para PROD.

Reglas duras:

- Nunca reutilizar `project` cruzado entre entornos.
- Nunca ejecutar deploy DEV con `.env.server` de PROD (ni viceversa).
- Nunca alternar `monstruo-dev` y `monstruo_dev` en `project` — rompe el ownership de Compose.

## Bootstrap inicial de una VM

### Requisitos

- `git`
- `docker` + `docker compose`

### Clonar el repo

```bash
sudo mkdir -p /srv/monstruo            # PROD: /srv/monstruo, DEV: /srv/monstruo_dev
sudo chown -R $USER:$USER /srv/monstruo
git clone git@github.com:JCtelconsulting/MONSTRUO.git /srv/monstruo
cd /srv/monstruo
git checkout main                      # DEV: git checkout dev
```

### Crear el `.env` del servidor (NO va a git)

```bash
mkdir -p plataforma/ops/env
# PROD:
cp plataforma/docs/operacion/deploy/plantillas_env/env.server.example plataforma/ops/env/.env.server
# DEV:
cp plataforma/docs/operacion/deploy/plantillas_env/env.server.dev.example plataforma/ops/env/.env.server.dev
```

Claves obligatorias para PROD:

- `SECRET_KEY` — largo y aleatorio, **no compartir con DEV**. Si queda vacío en PROD, el gateway aborta el arranque (`RuntimeError: SECRET_KEY inseguro en PROD`). Generar con `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`.
- `COOKIE_DOMAIN=.telconsulting.cl`
- `COOKIE_SECURE=1`

### Permisos: alinear UID/GID con el host

Los containers corren como `appuser` (no root). Por defecto `UID=1000`, `GID=1000`. Si en la VM el usuario que es dueño de los bind mounts (`./ticketera/data/...`, `./plataforma/data/...`) tiene un UID distinto, hay que parametrizar para evitar errores de permisos al escribir:

```bash
# Verificar UID del dueño de los archivos
id $(stat -c '%U' /srv/monstruo_dev/ticketera/data 2>/dev/null || echo $USER)

# Si UID != 1000, exportar antes de levantar:
export APP_UID=$(id -u)
export APP_GID=$(id -g)
```

Estas variables se leen al hacer `docker compose build` y se pasan como `ARG` al Dockerfile. Si no están seteadas, default es `1000`.

> **Migración primer deploy**: si los bind mounts (`ticketera/data/{tickets,compliance}`) fueron creados por containers anteriores que corrían como `root`, su ownership será de root y el nuevo `appuser` no podrá escribir. Arreglarlo sin `sudo` con un container temporal:
>
> ```bash
> docker run --rm -v /srv/monstruo/ticketera/data:/data alpine:3 chown -R $(id -u):$(id -g) /data
> ```
>
> (Reemplazar `/srv/monstruo` por la ruta de tu entorno; en DEV es `/srv/monstruo_dev`.)

### Levantar el stack

```bash
# PROD
cd /srv/monstruo
APP_UID=$(id -u) APP_GID=$(id -g) \
  ENV_FILE=plataforma/ops/env/.env.server STACK_NAME=monstruo \
  docker compose --env-file plataforma/ops/env/.env.server up -d --build

# DEV
cd /srv/monstruo_dev
APP_UID=$(id -u) APP_GID=$(id -g) docker compose up -d --build
# (usa defaults: STACK_NAME=monstruo-dev, ENV_FILE=plataforma/ops/env/.env.server.dev)
```

### Smoke test

```bash
# PROD (post-migración a 9001):
curl -fsS http://127.0.0.1:9001/health

# DEV:
curl -fsS http://127.0.0.1:9001/health
```

## Auto-deploy con GitHub Actions

Workflow: `.github/workflows/deploy.yml`. Corre en runner self-hosted en la VM de apps.

Por rama:

- `main` → despliega en `/srv/monstruo` con `ENV_FILE=plataforma/ops/env/.env.server`, `project=monstruo`
- `dev` → despliega en `/srv/monstruo_dev` con `ENV_FILE=plataforma/ops/env/.env.server.dev`, `project=monstruo_dev`

### Setup del runner (una vez por VM)

1. GitHub → Settings → Actions → Runners → New self-hosted runner.
2. Instalar en `192.168.60.5` (PROD) o `192.168.60.8` (DEV).
3. Usuario del runner debe estar en el grupo `docker`.
4. GitHub → Settings → Environments → crear `production` con "Required reviewers" para que cada deploy a `main` requiera aprobación.

## Flujo de trabajo recomendado

1. PC: branch desde `dev` → cambios → PR → merge a `dev`.
2. GitHub Actions despliega DEV automático.
3. Validar en DEV (`https://login.telconsulting.cl/dev/`).
4. Cuando DEV esté estable: PR `dev → main`, aprobación en GitHub, despliegue PROD automático.
5. Nginx solo enruta; no se toca al desplegar.

## Plantillas de entorno

Versionadas en `plataforma/docs/operacion/deploy/plantillas_env/`:

- `env.base.example` — base genérica
- `env.local.example` — para correr en PC sin docker (legacy, casi no se usa)
- `env.server.example` — PROD
- `env.server.dev.example` — DEV

Nunca subir `.env*` reales al repo (`.gitignore` ya los excluye).

## Verificar versión desplegada

La API expone `GET /version`:

```bash
curl -fsS http://127.0.0.1:9001/version
```

Devuelve `git_sha`, `branch`, `build_time`. Debe coincidir con el SHA del último run en GitHub Actions.
