# CLAUDE.md - MONSTRUO DEV

Reglas operativas canónicas: **[plataforma/docs/AGENTS.md](plataforma/docs/AGENTS.md)**.

Léelo primero. Lo de abajo es solo el resumen mínimo para arrancar.

## Contexto rápido

- **Prioridad actual:** GTA (Gestión y Tableros por Área)
- **Ticketera:** en producción y mantención post-PROD (EPIC 11 cerrado)
- **Rama base:** `dev` (nunca `main`/`prod` sin autorización explícita)
- **Entornos:**
  - DEV: `project=monstruo_dev`, env: `/srv/monstruo_dev/plataforma/ops/env/.env.server.dev`
  - PROD: `project=monstruo`, env: `/srv/monstruo/plataforma/ops/env/.env.server`

## Verificación al iniciar

```bash
git branch
grep "^project=" plataforma/ops/env/.env.server.dev
psql -c "SELECT version();" 2>/dev/null || echo "DB no disponible aún"
```

## Rebuild obligatorio tras cambios de código

**Siempre** rebuildear los containers afectados antes de declarar un cambio listo o pedirle al usuario que lo verifique. Esto incluye cambios en UI (HTML/CSS/JS), backend (Python), o cualquier otro código.

```bash
ASSET_VERSION=$(git rev-parse --short HEAD) \
  APP_UID=$(id -u) APP_GID=$(id -g) \
  docker compose --env-file plataforma/ops/env/.env.server.dev up -d --build <containers>
```

Luego validar runtime con `curl` al endpoint relevante antes de avisar al usuario.

**Por qué importa:** sin rebuild, `window.ASSET_VERSION` queda con el SHA anterior, el navegador sigue sirviendo HTML cacheado mientras el JS es nuevo, y se producen mismatches silenciosos (el JS busca IDs que ya no existen en el HTML cacheado). Síntoma típico: "no veo los cambios" o "no pasa nada al apretar".

Hacerlo **antes** del commit es mejor: detecta errores de sintaxis o imports rotos antes de pushear.

## Orden de autoridad (resumen)

1. `plataforma/docs/GUIA_MAESTRA.md`
2. `plataforma/docs/PROYECTO_CONTEXTO.md`
3. `plataforma/docs/AGENTS.md`
4. Instrucción puntual del usuario
