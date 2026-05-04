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

## Orden de autoridad (resumen)

1. `plataforma/docs/plan/GUIA_MAESTRA.md`
2. `plataforma/docs/PROYECTO_CONTEXTO.md`
3. `plataforma/docs/AGENTS.md`
4. Instrucción puntual del usuario
