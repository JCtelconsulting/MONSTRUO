# Contrato de Apps

Este documento define la estructura mínima aceptada para una app o módulo nuevo.

## Regla principal

Cada app debe elegir un patrón y mantenerse consistente.

No se aceptan híbridos improvisados dentro de la misma app.

## Patrón A: Servicio simple

Usar cuando el módulo expone backend liviano y UI simple.

Estructura mínima:
- `README.md`
- `Dockerfile`
- `main.py`
- `router.py`
- `service.py`
- `ui/`

Opcionales:
- `jobs/`
- `data/`
- `tests/`

Ejemplos cercanos:
- `bodega`
- `crm`
- `erp`

## Patrón B: App separada en backend/frontend

Usar cuando el módulo ya tiene separación real de backend y frontend.

Estructura mínima:
- `README.md`
- `Dockerfile`
- `backend/`
- `frontend/`

El backend debe tener al menos:
- `main.py`
- `router.py`
- `service.py` o equivalente claro

Ejemplos cercanos:
- `ticketera`
- `gateway`

## Reglas obligatorias

- toda app debe tener `README.md`
- toda app desplegable debe tener `Dockerfile`
- la lógica de negocio no debe quedar duplicada entre apps
- `PROD` y `DEV` se diferencian por configuración, no por copiar archivos
- una app nueva no debe crear otra estructura base distinta sin justificación explícita

## Datos y ownership

- si una app tiene `data/`, debe ser realmente propia
- datos compartidos van en `plataforma/`
- utilidades compartidas van en `plataforma/core/`, no copiadas entre módulos

## Proxy y publicación

- la publicación pública se documenta en `plataforma/docs/PROXY_INVERSO.md`
- los `conf` activos del proxy deben quedar versionados en `plataforma/ops/nginx/`

## Qué no hacer

- mezclar `main.py` en raíz con `backend/` a medias
- dejar assets públicos repartidos entre varias carpetas históricas sin dueño claro
- crear documentos de operación en la raíz del repo
- agregar rutas o Nginx “temporales” sin documentarlas
