# Activar Sentry para monitoreo de errores

## Por que

Sentry captura excepciones no capturadas del backend (500, errores en
handlers, etc.) y las envia a un dashboard donde se ven con stack trace,
contexto de la request y agrupadas. Esencial para detectar bugs en
produccion sin esperar a que un usuario reporte.

## Costo

Plan free de Sentry: 5K eventos/mes, retencion 30 dias. Para Terreneitor
con ~6 usuarios activos eso es **mas que suficiente** (probable: ~50-200
eventos/mes en estado normal, picos de 1-2K si hay un bug critico).

## Pasos (10 minutos)

### 1. Crear proyecto en Sentry

1. Ir a https://sentry.io/signup/ y crear cuenta (Sign up with GitHub
   funciona bien).
2. En el wizard de "Create Project":
   - Platform: **Python -> FastAPI**
   - Alert frequency: "Alert me on every new issue"
   - Project name: `terreneitor-prod`
   - Team: el default

3. En la siguiente pantalla, copiar el **DSN** (luce como
   `https://abc123@o456789.ingest.sentry.io/123456`).

### 2. Configurar el DSN en el servidor

Editar `/srv/terreneitor/ops/environments/.env` (NO commitear este
archivo, esta en .gitignore) y agregar:

```env
SENTRY_DSN=https://abc123@o456789.ingest.sentry.io/123456
```

### 3. Reiniciar el contenedor

```bash
docker restart terreneitor_app
```

### 4. Verificar

```bash
docker logs --tail 5 terreneitor_app | grep SENTRY
```

Deberias ver:
```
[SENTRY] Inicializado (env=production, traces=10%)
```

### 5. Disparar un evento de prueba

Hacer un request invalido para verificar que Sentry recibe:

```bash
curl http://localhost:8005/api/asignaciones/por-estado/INVALIDO
```

A los 10-30 segundos deberia aparecer un issue en el dashboard de Sentry.

## Configuracion aplicada

El codigo en `backend/core/cerebro.py` ya hace:
- **traces_sample_rate=0.1** en prod, 1.0 en dev. Captura performance del
  10% de las requests (para detectar lentitud sin saturar el plan free).
- **send_default_pii=False**: no envia datos personales por default.
- **before_send con _scrub_pii**: filtra body y cookies de requests
  antes de enviar (para no leakear passwords ni JWT).
- **release** desde env var `APP_VERSION` o `GIT_SHA` (opcional, util
  para asociar errores a versiones especificas).

## Setup de alertas recomendado

Una vez activo, en Sentry > Alerts:

1. **Alert nueva issue**: ya viene activo por default.
2. **Alert por spike de errores**: si hay >50 errores en 5 minutos -> mail.
3. **Integracion Slack** (opcional): si tienen workspace, agregar la
   integracion oficial. Asi los errores caen en un canal #alertas en
   tiempo real.

## Rotar el DSN

Si el DSN se filtra (commiteado por error, log expuesto, etc.):

1. Sentry > Project Settings > Client Keys (DSN) > Generate New Key.
2. Reemplazar en `.env` y reiniciar docker.
3. Revocar el viejo en la misma pantalla.
