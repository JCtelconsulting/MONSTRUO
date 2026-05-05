# Arquitectura del Sistema Monstruo

> **Última revisión**: 2026-05-05.
> Documentos relacionados: [PROXY_INVERSO.md](PROXY_INVERSO.md) (detalle del proxy), [CONTRATO_APPS.md](CONTRATO_APPS.md) (contrato que toda app debe cumplir), [FLUJO_REQUEST.md](FLUJO_REQUEST.md) (anatomía de un request).

## 1. Flujo de red

```
Usuario
  │
  ▼
Internet
  │
  ▼
VM Proxy (192.168.60.6 - PROXYSSL, Nginx 1.22.1 + TLS Let's Encrypt)
  │
  ├──→ VM apps PROD (192.168.60.5)  : 9001 (gateway/login/config), 9005 (ticketera api), 9006 (fundación api)
  ├──→ VM apps DEV  (192.168.60.8)  : 9001, 9005, 9006
  ├──→ VM IA        (192.168.20.228): 18789 (ia-app), 8000 (ia-oficina), 5173 (ultron front)
  └──→ Terreneitor  (192.168.60.5)  : 8080 (PROD), 8081 (DEV)
```

El proxy enruta por dominio:

- `*.telconsulting.cl` → según familia, ver [PROXY_INVERSO.md](PROXY_INVERSO.md) para tabla completa.
- PROD usa `/`, DEV usa `/dev/`.

## 2. Componentes Docker (por VM)

Stack orquestado por `docker-compose.yaml` en raíz del repo. Contrato canónico DEV/PROD parametrizado por `STACK_NAME`, `ENV_FILE`, `POSTGRES_DB`, `GATEWAY_PORT`, `TICKETERA_PORT`. Validado por `plataforma/tests/ci_repo_guard.py`.

| Servicio | Puerto interno | Imagen | Función |
|---|---|---|---|
| `db` | `5432` (NUNCA al host) | `postgres:16` | Base de datos central, schemas por app (`auth`, `ops`, `tks`, `gta`, `crm`, `erp`, `bodega`, `fundacion`, `pmo`) |
| `gateway` | `9001` | `monstruo-gateway` | Punto de entrada, auth, RBAC, proxy a apps internas |
| `ticketera` | `9005` | `monstruo-ticketera` | API y UI de tickets |
| `gta` | `9012` | `monstruo-gta` | Gestión de Tareas Automatizadas (prioridad actual) |
| `crm` | `9007` | `monstruo-crm` | CRM clientes |
| `erp` | `9008` | `monstruo-erp` | Facturación + conciliación bancaria |
| `bodega` | `9009` | `monstruo-bodega` | Inventario |
| `fundacion` | `9006` | `monstruo-fundacion` | Módulo Fundación |
| `pmo` | `9010` | `monstruo-pmo` | Gestión de proyectos |
| `ia` | `9011` | `monstruo-ia` | Servicios IA |
| `zabbix` | `9013` | `monstruo-zabbix` | Integración Zabbix |

> Verificar puertos exactos en `docker-compose.yaml`. Algunos como `pmo`, `zabbix` pueden no estar productivos aún.

## 3. Modelo de aplicaciones

Cada app es **autocontenida** y sigue el mismo contrato (ver [CONTRATO_APPS.md](CONTRATO_APPS.md)):

```
<app>/
├── backend/
│   ├── main.py                # FastAPI app
│   ├── router.py              # Endpoints /api/<app>/*
│   ├── services/              # Lógica de negocio (propia, no compartida)
│   └── jobs/                  # Workers/jobs específicos
├── ui/                        # HTML + JS + CSS (servido por gateway)
├── migrations/                # SQL versionado (cuando aplica)
├── docs/                      # Documentación de la app
├── tests/
├── data/                      # Runtime data (no a git)
├── Dockerfile
├── README.md
└── requirements.txt
```

## 4. Plataforma compartida (`plataforma/core/`)

Solo lógica genuinamente transversal. **Lo específico de una app vive en la app**, no acá. Contenido actual:

- `db.py` — conexión, schemas, migraciones DDL
- `security.py` — hashing, tokens
- `middleware.py` — middlewares HTTP comunes
- `auth_service.py` — autenticación
- `config.py` — settings globales
- `deps.py` — dependencies de FastAPI (sesiones, permisos)
- `email.py` + `email_integration.py` — envío y polling de correo
- `google_chat.py` — notificaciones Google Chat
- `notifications.py` — sistema de notificaciones in-app
- `jobs_engine.py` — motor de jobs persistente con retry/DLQ
- `audit.py` + `audit_decorator.py` — auditoría con decorador
- `migrations.py` — runner de migraciones
- `env_loader.py` — carga de `.env.server.dev`/`.env.server`
- `web.py` — utilidades web compartidas
- `ai/` — bridge a IA local (OpenAI-compat) + políticas y prompts

> **Histórico**: hasta principios de 2026 hubo `tickets_service.py`, `bodega_service.py`, `crm_service.py` duplicados aquí y en cada app, lo que generaba acoplamiento. Esa refactorización ya se completó: la lógica vive solo en cada app.

## 5. Comunicación entre apps

Por API HTTP a través del gateway. **No hay imports cruzados** entre apps (`from ticketera import ...` desde otra app está prohibido). El gateway es el único que conoce todos los servicios y enruta entre ellos.

Para flujo detallado de un request, ver [FLUJO_REQUEST.md](FLUJO_REQUEST.md).

## 6. Pendientes de evolución

- **Proxy local por VM**: hoy ambos entornos dependen del proxy compartido en `192.168.60.6`. Una evolución posible es que cada VM apps tenga su propio Nginx local que termine TLS, eliminando esa dependencia. No hay plan concreto en curso.
- **Algunos dominios declarados sin backend**: `pmo`, `erp`, `crm`, `bodega`, `zabbix`, `monitoreo` aparecen como `server_name` en `monstruo.conf` pero hay que confirmar caso por caso si el `proxy_pass` apunta a backend real o es stub esperando despliegue.
