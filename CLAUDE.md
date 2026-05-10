# CLAUDE.md - MONSTRUO DEV

Reglas operativas canónicas: **[AGENTS.md](AGENTS.md)** (raíz del repo, válido para cualquier agente).

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

**Usar siempre el script `scripts/dev-rebuild.sh`** — maneja `ASSET_VERSION` correctamente para cache-busting:

```bash
./scripts/dev-rebuild.sh                   # rebuild todos los containers
./scripts/dev-rebuild.sh gateway gta       # rebuild solo gateway+gta
```

El script detecta si el árbol git está sucio (cambios sin commit) y agrega un timestamp al `ASSET_VERSION`, garantizando que el browser recargue assets nuevos. Si el árbol está limpio, usa el SHA del commit.

Luego validar runtime con `curl` al endpoint relevante antes de avisar al usuario.

**Por qué importa:** sin un `ASSET_VERSION` único por rebuild, el navegador sigue sirviendo el HTML/JS/CSS cacheado mientras el código del container es nuevo, y se producen mismatches silenciosos (el JS busca IDs que ya no existen en el HTML cacheado). Síntoma típico: "no veo los cambios" o "no pasa nada al apretar".

**Antipatrón conocido:** `ASSET_VERSION=$(git rev-parse --short HEAD)` solo funciona si commiteás antes de rebuildar. Durante desarrollo iterativo (cambios sin commit), el SHA queda igual y el cache no se rompe. **Por eso usamos `dev-rebuild.sh`** en lugar de la receta directa de docker compose.

Hacerlo **antes** del commit es mejor: detecta errores de sintaxis o imports rotos antes de pushear.

## Orden de autoridad (resumen)

1. `plataforma/docs/GUIA_MAESTRA.md`
2. `plataforma/docs/PROYECTO_CONTEXTO.md`
3. `AGENTS.md` (raíz)
4. Instrucción puntual del usuario
