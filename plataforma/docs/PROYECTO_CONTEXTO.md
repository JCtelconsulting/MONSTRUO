# Proyecto Contexto — Monstruo (central)

> Solo lo puntual. El detalle de cada módulo vive en su `<modulo>/ESTADO.md`.
> Historia cronológica: [CHANGELOG.md](CHANGELOG.md). Versión anterior de este
> doc: [antiguo/PROYECTO_CONTEXTO-hasta-2026-06-12.md](antiguo/PROYECTO_CONTEXTO-hasta-2026-06-12.md).

**Actualizado:** 2026-06-12

## Qué es esto

Ecosistema **Monstruo** de Telconsulting: un login central (gateway) + módulos
(ticketera, terreneitor, fundación, gta, erp/crm/bodega/pmo/ia/zabbix) sobre un
Postgres central (schema por módulo) en la VM DEV `192.168.60.8`. Identidad
visual **Premium Gold** ([design.md](design.md) + [manual de marca](manual-marca-telconsulting.md)).

## Reglas de oro

- Rama de trabajo única: **`dev`** (origin/dev). `main` = producción (deploy CI).
- DEV publica con prefijo `/dev/`; PROD sin prefijo. Nunca mezclar.
- Leer `AGENTS.md` (raíz) antes de operar. UN solo agente por repo a la vez.
- Prioridad de negocio: **EPIC 11 (Ticketera)** hasta su Go/No-Go.

## Estado por módulo (detalle en cada ESTADO.md)

| Módulo | Estado | Doc |
|---|---|---|
| Ticketera | 🟡 hotfix IMAP integrado; falta casilla real + E2E + Go/No-Go | [ticketera/ESTADO.md](../../ticketera/ESTADO.md) |
| Terreneitor | 🟢 módulo pleno (URL única, SSO, Postgres); falta réplica PROD | [terreneitor/ESTADO.md](../../terreneitor/ESTADO.md) |
| Fundación | 🔴 código nuevo en rama archivo; dev y contenedor corren versión vieja | [fundacion/ESTADO.md](../../fundacion/ESTADO.md) |
| GTA | 🔴 código en rama archivo; contenedor legacy corre la versión nueva | [gta/ESTADO.md](../../gta/ESTADO.md) |
| Gateway/Plataforma | 🟢 SSO, barra compartida, dorado, dashboard lanzadera | [plataforma/ESTADO.md](../ESTADO.md) |
| ERP/CRM/Bodega/PMO/IA/Zabbix | ⚪ stubs/placeholder, sin desarrollo activo | — |

## DECISIONES PENDIENTES (lo más importante)

1. **Fusionar la línea archivada a `dev`** — `archivo/dev-pre-regularizacion-20260612`
   tiene ~89 commits de GTA + Fundación (planificación, calendario, refactor
   ticketera a package) que NO están en `dev`. Es la tarea #1 del próximo
   agente: merge con resolución de conflictos (ticketera service.py monolito vs
   package; frontend del gateway divergido). Hasta entonces, Fundación corre
   versión vieja y GTA vive solo en su contenedor legacy.
2. **Casilla de correo real para dev** (ticketera): IMAP/SMTP vacíos en
   Configuración; MAIL_SANDBOX=true. Sin eso no se puede validar el flujo de
   correo de punta a punta.
3. **Terreneitor a PROD**: replicar la migración en la 60.5 con ventana +
   resolver colisión de cookie `access_token` (plan en
   `terreneitor/docs/MIGRACION_MONSTRUO.md`).
