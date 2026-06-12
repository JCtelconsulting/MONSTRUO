# Monstruo DEV — Mapa del ecosistema

Ecosistema de aplicaciones de **Telconsulting**: un login central + módulos,
una base Postgres (schema por módulo), identidad **Premium Gold**.
Este README es el punto de entrada: en 5 minutos te sitúas.

> Agentes: leer **[AGENTS.md](AGENTS.md)** antes de tocar nada.
> Estado puntual del proyecto: **[plataforma/docs/PROYECTO_CONTEXTO.md](plataforma/docs/PROYECTO_CONTEXTO.md)**.

## Módulos y URLs (DEV usa prefijo `/dev/`)

| Módulo | URL (dev) | Puerto | Estado |
|---|---|---|---|
| Login / Gateway (SSO) | login.telconsulting.cl/dev | 9001 | [plataforma/ESTADO.md](plataforma/ESTADO.md) |
| Dashboard (lanzadera) | login.telconsulting.cl/dev/dashboard | 9001 | ídem |
| Ticketera | ticketera.telconsulting.cl/dev | 9005 | [ticketera/ESTADO.md](ticketera/ESTADO.md) |
| Terreneitor | terreneitor.telconsulting.cl/dev | 8005 | [terreneitor/ESTADO.md](terreneitor/ESTADO.md) |
| Fundación | login.telconsulting.cl/dev/fundacion | 9006 | [fundacion/ESTADO.md](fundacion/ESTADO.md) |
| GTA | (legacy, fuera del compose) | 9012 | [gta/ESTADO.md](gta/ESTADO.md) |
| Configuración | config.telconsulting.cl/dev | 9001 | — |
| ERP/CRM/Bodega/PMO/IA/Zabbix | stubs | 9006-9011 | sin desarrollo activo |

## Cómo se levanta

```bash
# Stack principal (db + gateway + ticketera + fundacion)
docker compose --env-file plataforma/ops/env/.env.server.dev up -d --build

# Terreneitor (módulo con compose propio, misma red)
docker compose -f terreneitor/docker-compose.yaml up -d --build
```

- Postgres central: contenedor `monstruo-dev-db` (NUNCA publica 5432 al host).
- Env DEV: `plataforma/ops/env/.env.server.dev` (secretos: no commitear).
- Proxy público: VM 192.168.60.6 (nginx) → esta VM (60.8). Config versionada
  en `plataforma/ops/nginx/`.

## Git

- Rama de trabajo única: **`dev`**. `main` = producción (deploy automático CI).
- Flujo: commits chicos a dev → push → (PROD: merge a main con autorización).
- ⚠️ Hay una línea archivada pendiente de fusionar:
  `archivo/dev-pre-regularizacion-20260612` (GTA + Fundación). Ver
  PROYECTO_CONTEXTO → Decisiones pendientes.

## Documentación

| Qué buscas | Dónde |
|---|---|
| Estado actual y decisiones | [plataforma/docs/PROYECTO_CONTEXTO.md](plataforma/docs/PROYECTO_CONTEXTO.md) + `<modulo>/ESTADO.md` |
| Prioridades de negocio (EPICs) | [plataforma/docs/GUIA_MAESTRA.md](plataforma/docs/GUIA_MAESTRA.md) |
| Arquitectura y red | [plataforma/docs/ARQUITECTURA.md](plataforma/docs/ARQUITECTURA.md) |
| Proxy / dominios | [plataforma/docs/PROXY_INVERSO.md](plataforma/docs/PROXY_INVERSO.md) |
| Línea visual + marca | [plataforma/docs/design.md](plataforma/docs/design.md) + [manual de marca](plataforma/docs/manual-marca-telconsulting.md) |
| Reglas para apps nuevas | [plataforma/docs/CONTRATO_APPS.md](plataforma/docs/CONTRATO_APPS.md) |
| Historia | [plataforma/docs/CHANGELOG.md](plataforma/docs/CHANGELOG.md) · viejo: `plataforma/docs/antiguo/` |

## Documentación

- Índice completo de docs: [plataforma/docs/README.md](plataforma/docs/README.md)
- Arquitectura AS-IS: [plataforma/docs/arquitectura/ARQUITECTURA.md](plataforma/docs/arquitectura/ARQUITECTURA.md)
- Bitácora por mes: [plataforma/docs/changelog/](plataforma/docs/changelog/)
