# Plantillas de Entorno

Plantillas versionadas de variables de entorno. Los `.env` reales viven en `plataforma/ops/env/` (gitignored).

## Archivos

- `env.server.example` — PROD. Copiar a `plataforma/ops/env/.env.server`.
- `env.server.dev.example` — DEV / staging interno. Copiar a `plataforma/ops/env/.env.server.dev`.

## Uso

```bash
# DEV
cp plataforma/docs/operacion/plantillas_env/env.server.dev.example plataforma/ops/env/.env.server.dev

# PROD
cp plataforma/docs/operacion/plantillas_env/env.server.example plataforma/ops/env/.env.server
```

Después editar el archivo copiado para reemplazar los `replace_me` y placeholders.

Ver [GUIA_DEPLOY.md](../GUIA_DEPLOY.md) para el flujo completo.
