# Arquitectura del Ecosistema Monstruo (AS-IS)

**Actualizado:** 2026-06-12

## 1. Topología de red

```
Usuario ──► Internet ──► VM Proxy nginx (192.168.60.6)
                              │   *.telconsulting.cl ; DEV = /dev/, PROD = /
              ┌───────────────┼───────────────────────┐
              ▼                                       ▼
   VM PROD (192.168.60.5)                  VM DEV (192.168.60.8)  ← esta VM
   - Monstruo monolito :9000               - gateway        :9001 (login/SSO/dashboard/config)
     (ticketera/login/config)              - ticketera      :9005
   - Terreneitor legado :8080              - fundacion      :9006
                                           - terreneitor    :8005 (módulo, compose propio)
                                           - gta (legacy)   :9012 (fuera del compose)
                                           - postgres 16    (interno, sin puerto host)
```

- El proxy versiona su config en `plataforma/ops/nginx/` (debe ir sincronizada
  con la VM 60.6). OJO: inyecta `<base>` solo en la raíz exacta de cada
  dominio; por eso Terreneitor REDIRIGE su raíz al hub en vez de servir HTML.

## 2. Plataforma común

- **Postgres central** (`monstruo-dev-db`, DB `monstruo_dev`): un schema por
  módulo (`auth`, `core`, `tks`, `fundacion`, `gta`, `terreneitor`, …).
- **Auth/SSO**: el gateway emite JWT HS256 en cookie `access_token`
  (dominio `.telconsulting.cl`); usuarios y permisos en `auth.users`
  (`role`, `secondary_roles`, `allowed_modules`). Los módulos validan el token
  localmente (`plataforma/core/security.py`); Terreneitor lo valida con
  `MONSTRUO_SSO_SECRET` y autoriza contra `auth.users` (requiere
  `"terreneitor"` en allowed_modules o rol admin) auto-provisionando un usuario
  espejo local.
- **Shell compartida**: `gateway/frontend/shared/ui/` (monstruo.css + sidebar.js
  + utilidades.js). Los módulos del gateway la sirven en `/shared/*`;
  Terreneitor la consume vía proxy interno (`/shared/{path}` → gateway:9001),
  por eso la barra es idéntica en todo el ecosistema sin copias.
- **Jobs**: `plataforma/core/jobs_engine.py` con handlers registrados por cada
  módulo en su `main.py`; cola en `core.sys_jobs` (Postgres).
- **Identidad visual**: Premium Gold (ver `design.md` + manual de marca);
  marca de agua del cubo vía `body::after` en monstruo.css.

## 3. Terreneitor como módulo (particularidades)

- Vive en `terreneitor/` con **compose propio** unido a la red
  `monstruo-dev_default`; repo fuente de verdad separado (GitHub TERRENEITOR,
  rama `dev`, working copy en `/srv/terreneitor_dev`).
- URL única `terreneitor.telconsulting.cl` → raíz redirige a `/modulos/hub/`
  (tarjetas por rol); módulos internos en `/modulos/{terreno,supervisor,
  gerencia,portal}/`; subdominios antiguos → 307.
- Backend FastAPI propio (no usa `plataforma/core`); conexión a Postgres por
  `TERRENEITOR_DATABASE_URL` (sin la var → SQLite standalone, su rollback).
- Archivos (fotos de terreno) en disco: `terreneitor/data/files/`.

## 4. Deuda / riesgos conocidos

- **Línea archivada sin fusionar** (`archivo/dev-pre-regularizacion-20260612`):
  GTA completo + Fundación nueva + refactor ticketera a package. Decisión #1 en
  PROYECTO_CONTEXTO.
- Dockerfiles copian TODO el repo (sin imagen base común): cualquier cambio
  invalida todas las imágenes.
- Cookie `access_token` compartida entre Monstruo y Terreneitor legado en PROD
  (colisión a resolver antes de migrar Terreneitor a PROD).
- `gta` corre fuera del compose (contenedor legacy intocable hasta el merge).
