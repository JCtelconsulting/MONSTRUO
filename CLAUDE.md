# CLAUDE.md - MONSTRUO DEV

Instrucciones para Claude Code en este repositorio. Lee también [AGENTS.md](AGENTS.md) para reglas operativas completas.

## Contexto rápido

- **Proyecto:** Ticketera interna (EPIC 11)
- **Rama base:** `dev` (nunca `main`/`prod` sin autorización explícita)
- **Entornos:**
  - DEV: `project=monstruo_dev`, env: `/srv/monstruo_dev/plataforma/ops/env/.env.server.dev`
  - PROD: `project=monstruo`, env: `/srv/monstruo/plataforma/ops/env/.env.server`

## Reglas obligatorias

1. **Separación DEV/PROD:** No mezclar credenciales, URLs ni deployments entre entornos.
2. **Una tarea a la vez:** Plan → Ejecución → Verificación → Cierre.
3. **Sin extras:** No meter cambios fuera de scope antes de cerrar la tarea.
4. **Seguridad:** Prohibido exponer secretos, no subir `.env*` ni credenciales.
5. **Git:** Commits pequeños, mensaje claro, scope único. Subir a `origin/dev`.
6. **Excluir de commits:** `data/`, archivos temporales, backups.

## Autoridad

En conflicto, seguir este orden:
1. `plataforma/docs/PLAN_MAESTRO_MONSTRUO.md`
2. `plataforma/docs/PROYECTO_CONTEXTO.md`
3. `AGENTS.md`
4. Instrucción puntual del usuario

## Verificación al iniciar

```bash
# Confirmar rama
git branch

# Confirmar entorno
grep "^project=" plataforma/ops/env/.env.server.dev

# Confirmar conexión a DB
psql -c "SELECT version();" 2>/dev/null || echo "DB no disponible aún"
```

## Contacto

Para dudas sobre reglas o contexto, consultar `plataforma/docs/PROYECTO_CONTEXTO.md`.
