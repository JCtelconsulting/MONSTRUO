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
│   └── rebuild.log        — log de ejecuciones (NO se commitea, .gitignore)
├── agents/                — subagentes especializados
│   └── code-reviewer.md
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

## Subagentes

### `code-reviewer`

Revisor read-only para usar antes de commits importantes o cuando se pida una
segunda opinión. Conoce las reglas duras del repo (DEV/PROD, cache-busting,
audit-logs append-only, etc.) y reporta hallazgos clasificados como
🔴 BLOQUEANTE / 🟡 IMPORTANTE / 🟢 SUGERENCIA. No edita ni reescribe código.

Invocación típica: el agente principal lo llama vía la tool `Agent` con
`subagent_type: "code-reviewer"` cuando termina un cambio significativo.

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
