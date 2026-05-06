# .claude/

Configuración específica de Claude Code para este repo. Se commitea al repo
para que cualquier sesión que abra Claude Code en `/srv/monstruo_dev` la
herede automáticamente.

## Estructura

```text
.claude/
├── settings.json       — config compartida del proyecto (hooks, permisos)
├── settings.local.json — config tuya local (NO se commitea, .gitignore)
├── hooks/              — scripts ejecutados por hooks
│   ├── rebuild-on-edit.sh
│   └── rebuild.log     — log de ejecuciones (NO se commitea, .gitignore)
└── (futuro)
    ├── agents/         — subagentes especializados
    └── commands/       — slash commands del proyecto
```

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

## Convenciones

- **Reglas operativas** (válidas para cualquier agente, no solo Claude)
  viven en `AGENTS.md` en la raíz. `CLAUDE.md` apunta a ellas.
- **Cosas específicas de Claude Code** (hooks, subagentes, slash commands)
  van aquí.
