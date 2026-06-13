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
| GTA | vía gateway · /gta | 9012 | [gta/ESTADO.md](gta/ESTADO.md) |
| Configuración | config.telconsulting.cl/dev | 9001 | — |
| ERP · CRM · Bodega | compose único | 9009 · 9008 · 9007 | activos (ERP=Laudus/SII, Bodega=kardex, CRM) |
| PMO · IA · Zabbix | compose único | 9010 · 9011 · 9013 | placeholders en construcción |

## Cómo se levanta

```bash
# Compose ÚNICO: todos los módulos en un solo stack
# (db + gateway + ticketera + fundacion + terreneitor + gta + erp/crm/bodega/pmo/ia/zabbix)
docker compose --env-file plataforma/ops/env/.env.server.dev up -d --build

# Rebuild de containers puntuales (maneja ASSET_VERSION para cache-busting):
./plataforma/ops/scripts/dev-rebuild.sh gateway gta
```

- Postgres central: contenedor `monstruo-dev-db` (NUNCA publica 5432 al host).
- Env DEV: `plataforma/ops/env/.env.server.dev` (secretos: no commitear).
- Proxy público: VM 192.168.60.6 (nginx) → esta VM (60.8). Config versionada
  en `plataforma/ops/nginx/`.

## Git

- Rama de trabajo única: **`dev`**. `main` = producción (deploy automático CI).
- Flujo: commits chicos a dev → push → (PROD: merge a main con autorización).

## Documentación

| Qué buscas | Dónde |
|---|---|
| Estado actual y decisiones | [plataforma/docs/PROYECTO_CONTEXTO.md](plataforma/docs/PROYECTO_CONTEXTO.md) + `<modulo>/ESTADO.md` |
| Prioridades de negocio (EPICs) | [plataforma/docs/GUIA_MAESTRA.md](plataforma/docs/GUIA_MAESTRA.md) |
| Arquitectura y red | [plataforma/docs/arquitectura/ARQUITECTURA.md](plataforma/docs/arquitectura/ARQUITECTURA.md) |
| Proxy / dominios | [plataforma/docs/arquitectura/PROXY_INVERSO.md](plataforma/docs/arquitectura/PROXY_INVERSO.md) |
| Línea visual + marca | [plataforma/docs/design.md](plataforma/docs/design.md) + [manual de marca](plataforma/docs/manual-marca-telconsulting.md) |
| Reglas para apps nuevas | [plataforma/docs/CONTRATO_APPS.md](plataforma/docs/CONTRATO_APPS.md) |
| Historia | [plataforma/docs/CHANGELOG.md](plataforma/docs/CHANGELOG.md) · viejo: `plataforma/docs/antiguo/` |

## Documentación

- Índice completo de docs: [plataforma/docs/README.md](plataforma/docs/README.md)
- Arquitectura AS-IS: [plataforma/docs/arquitectura/ARQUITECTURA.md](plataforma/docs/arquitectura/ARQUITECTURA.md)
- Bitácora por mes: [plataforma/docs/changelog/](plataforma/docs/changelog/)
