# Contrato de Apps

Estructura mínima que toda app del repo debe respetar para mantener consistencia operacional y poder desplegarse, monitorearse y mantenerse igual que las demás.

## Estructura estándar

Una app es una carpeta de primer nivel del repo (`gateway/`, `ticketera/`, `gta/`, `crm/`, `erp/`, `bodega/`).

Layout mínimo:

```
<app>/
├── README.md
├── Dockerfile
├── requirements.txt
├── backend/
│   ├── __init__.py
│   ├── main.py            # FastAPI app, lifespan, init_db
│   └── router.py          # endpoints /api/<app>/...
├── ui/                    # HTML + JS + CSS, servido por gateway
├── migrations/            # SQL versionado por app (cuando aplica)
├── tests/
└── data/                  # runtime data (gitignored)
```

Cuando hay lógica significativa, agregar:

```
backend/
├── services/              # lógica de negocio
│   └── service.py         # o paquete service/ para apps grandes
└── jobs/                  # workers/jobs específicos
```

## Reglas obligatorias

- Toda app tiene `README.md` y `Dockerfile`.
- `Dockerfile` usa `python:3.12-slim` con el patrón estándar (instalación deps, `COPY` en orden óptimo de cache, `uvicorn` como entrypoint).
- Puerto interno único por app, declarado en `docker-compose.yaml`.
- `PROD` y `DEV` se diferencian por configuración (env files), nunca por copiar archivos o duplicar código.
- Lógica de negocio NO duplicada entre apps. Si dos apps necesitan lo mismo, el código va a `plataforma/core/`.

## Comunicación entre apps

**Regla general**: las apps se comunican por HTTP a través del gateway. No imports cruzados directos.

**Excepciones documentadas y aceptadas**:

- `erp` importa de `bodega.backend.services.service` para descontar stock al emitir factura.
- `crm` importa de `erp.backend.services.sales_service` para mostrar facturas/deuda del cliente en su ficha.

Estas excepciones son lecturas/llamadas de servicio sincrónicas y vienen del mismo dominio comercial (cliente → factura → stock). Refactorizarlas a HTTP agregaría latencia y complejidad sin beneficio claro mientras compartan el mismo Postgres.

**No agregar nuevos cross-app imports sin justificación**. Si aparece la necesidad, primero evaluar:
1. ¿Se puede mover la lógica compartida a `plataforma/core/`?
2. ¿Vale la pena exponer un endpoint HTTP en la app dueña?
3. ¿Es realmente la misma transacción de negocio o son dominios distintos?

## Plataforma compartida

Solo va en `plataforma/core/` lo que es genuinamente transversal:

- Auth, RBAC, sesión.
- Acceso a base de datos y migraciones.
- Motor de jobs persistente.
- Email, notificaciones in-app, Google Chat.
- Auditoría y evidencias.
- Middlewares HTTP y utilidades web.

Lo específico de una app vive en la app, no acá.

## Migraciones

- DDL principal hoy vive en `plataforma/core/db.py` (`init_db()` lo ejecuta al arrancar).
- Las migraciones SQL en `<app>/migrations/` son scripts ad-hoc (DROP TABLE, ALTER, fixtures) que se corren manualmente cuando hace falta. No se aplican automáticamente.
- Naming: `NNN_descripcion.sql` (3 dígitos). Idempotente (`IF NOT EXISTS` / `IF EXISTS`).

## Proxy y publicación

- Las configs activas del proxy están versionadas en `plataforma/ops/nginx/`.
- La publicación pública se documenta en [PROXY_INVERSO.md](PROXY_INVERSO.md).
- Una app declarada en `monstruo.conf` con `server_name` pero sin `proxy_pass` real es un placeholder reservado, no un bug.

## Qué no hacer

- Mezclar `main.py` en raíz de la app con `backend/main.py` a medias.
- Crear documentos operativos en la raíz del repo.
- Agregar rutas o configs Nginx "temporales" sin actualizar este contrato y `PROXY_INVERSO.md`.
- Importar de otra app si no está en la lista de excepciones documentadas arriba.
