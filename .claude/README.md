# .claude/

Configuración específica de Claude Code para este repo. Se commitea al repo
para que cualquier sesión que abra Claude Code en `/srv/monstruo_dev` la
herede automáticamente.

## Estructura

```text
.claude/
├── settings.json          — config compartida (hooks, permisos)
├── settings.local.json    — config tuya local (NO se commitea, .gitignore)
├── hooks/                 — scripts ejecutados por hooks
│   ├── rebuild-on-edit.sh
│   ├── pre-push-checks.sh
│   ├── rebuild.log        — log (gitignored)
│   └── pre-push.log       — log (gitignored)
├── agents/                — subagentes especializados
│   ├── code-reviewer.md
│   └── migration-tester.md
├── commands/              — slash commands del proyecto
│   └── deploy-dev.md
└── mcp/                   — wrappers para MCP servers
    └── postgres-wrapper.sh
```

El `.mcp.json` que registra los MCP servers vive en la raíz del repo (no acá),
porque esa es la convención que Claude Code busca.

## Hooks activos

### `rebuild-on-edit` (PostToolUse: Edit|Write)

Tras editar archivos `.py`/`.html`/`.css`/`.js` en una de las apps
(`gateway/`, `gta/`, `ticketera/`, etc.), dispara un rebuild en background
del container correspondiente con `ASSET_VERSION=$(git rev-parse --short HEAD)`.

**Por qué:** evita el síntoma "no veo los cambios" cuando se olvida hacer
`docker compose up -d --build` después de editar código. Documentado como
regla en `AGENTS.md` §5.1; este hook la automatiza.

**Logs:** `.claude/hooks/rebuild.log` (gitignored).

**Excluye:**

- Archivos en `.claude/`, `plataforma/docs/`, raíz del repo (`AGENTS.md`,
  `README.md`, `docker-compose.yaml`, etc.).
- Extensiones que no son runtime: `.md`, `.json`, `.yaml`, `.sql`, etc.

### `pre-push-checks` (PreToolUse: Bash filtrando `git push`)

Antes de cada `git push` ejecutado vía Claude Code, dispara controles
automáticos sobre los commits en `origin/<branch>..HEAD`:

1. **code-reviewer** — siempre.
2. **migration-tester** — solo si el diff toca `plataforma/core/db.py`,
   `<app>/migrations/*.sql` o cualquier `*.sql`.

Si alguno reporta 🔴 BLOQUEANTE, el push se aborta (exit 2) y el agente
principal recibe instrucciones para mostrarte el reporte y pedirte
decisión antes de reintentar.

Filtra explícitamente: `git push --help`, `git push --dry-run`, `git pushd`,
y comandos que no empiezan con `git push`. Si no hay commits ahead vs
upstream, deja pasar (push vacío).

**Logs:** `.claude/hooks/pre-push.log` (gitignored).

## Subagentes

### `code-reviewer`

Revisor read-only de cualquier diff (típicamente `origin/dev..HEAD`).
Conoce las reglas duras del repo (DEV/PROD, cache-busting, audit-logs
append-only, etc.) y reporta hallazgos clasificados como 🔴 BLOQUEANTE
/ 🟡 IMPORTANTE / 🟢 SUGERENCIA. No edita ni reescribe código.

Invocación: automática por el hook `pre-push-checks` antes de cada push.
También puede invocarse manualmente: `subagent_type: "code-reviewer"`.

### `migration-tester`

Validador de migraciones DDL contra la DB de PROD (`192.168.60.5`,
container `monstruo-db`). Hace `pg_dump --schema-only` de PROD vía SSH,
levanta un container Postgres sandbox local con ese schema, aplica las
migraciones nuevas (correr `init_db()` de `plataforma/core/db.py` y/o
`<app>/migrations/*.sql`), compara resultados y reporta regresiones.

PROD se toca solo en lectura (`pg_dump`). El sandbox se destruye siempre
(trap EXIT).

Invocación: automática por el hook `pre-push-checks` SOLO cuando el diff
toca `plataforma/core/db.py`, `<app>/migrations/*.sql` o `*.sql`. Si no
hay cambios DDL, no se ejecuta (ahorra los 30-60s de validación).

## Slash commands

### `/deploy-dev <containers>`

Atajo para el ciclo `ASSET_VERSION=$(sha) docker compose up -d --build` +
smoke test de `/health`. Sin args, rebuildea el stack completo.

```text
/deploy-dev gateway gta
```

## MCP servers

### `monstruo-postgres`

MCP server oficial de Postgres (`@modelcontextprotocol/server-postgres`)
conectado a la DB DEV. Expone `tools` para hacer queries SQL y `resources`
para listar tablas/schemas, sin tener que pasar por `docker exec ... psql`
cada vez.

El wrapper `mcp/postgres-wrapper.sh` resuelve la IP del container
`monstruo-dev-db` en runtime (la IP cambia al recrear el container) y lee
las credenciales desde el env file del repo.

Configurado en `.mcp.json` (raíz del repo, scope proyecto).

## Convenciones

- **Reglas operativas** (válidas para cualquier agente, no solo Claude)
  viven en `AGENTS.md` en la raíz. `CLAUDE.md` apunta a ellas.
- **Cosas específicas de Claude Code** (hooks, subagentes, slash commands)
  van aquí.
