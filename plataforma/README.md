# Plataforma Core (SDK Interno)

Este directorio conforma la "Librería Central" de MONSTRUO. Alberga herramientas comunes que permiten a todas las aplicaciones mantener estandarización técnica sin duplicación de código ni lógica cruzada.

## Objetivo
Unificar las utilidades transversales como seguridad, comunicación a bases de datos, envío de correos, jobs y middleware, de manera agnóstica a la lógica de los servicios que las consumen.

## Componentes Técnicos
Este SDK se expone a otras aplicaciones mediante la importación local (usando el `PYTHONPATH=/app:/app/plataforma`). Ningún archivo dentro de esta carpeta debe ser importado de forma cruzada por otra aplicación más allá de funciones o utilidades permitidas. La estructura está compuesta por:

1.  **Conexiones Base (`core/db.py`)**: Centraliza y agrupa toda la conexión inicial al ORM, configuración de variables de entorno y utilidades para obtener el `conn`. Todos los microservicios comparten la misma base PostgreSQL en producción (actualmente).
2.  **Autenticación y Seguridad (`core/security.py`, `core/auth_service.py`)**: Utilidades de cifrado (passwords hash) y validación/decodificación JWT que es instanciada desde el Gateway.
3.  **Core Middleware (`core/middleware.py`)**: Gestiona las restricciones de rutas web como interceptores (Ej. `AuthIdentityMiddleware`).
4.  **Gestión de Integración y Mail (`core/email_integration.py`)**: Helpers unificados para despachar (SMTP) e ingerir (IMAP) correos que la `Ticketera` utiliza para sus procesos de automatización y notificaciones en hilo.
5.  **Motor de Background Jobs (`core/jobs_engine.py`)**: Maneja el enrutamiento y registro periódico en base de datos (`sys_jobs`) de los trabajos asíncronos programados como validación de SLA, purgado y métricas.
6.  **Dependencias (`core/deps.py`)**: Exposición de los requerimientos para asegurar la seguridad (`Depends(deps.require_session_hybrid)`) inyectable en las rutas de FastAPI.

## Regla de Oro Arquitectónica
**Prohibida la lógica de negocio.**
En esta carpeta **NO DEBEN EXISTIR** archivos como `bodega_service.py` o herramientas ligadas al dominio de las aplicaciones que la componen (ej. gestión de clientes, lógica contable). Para eso cada aplicación mantiene un directorio `backend/services/`.

## Gestión de Operaciones y Backups (`ops/` y `data/`)
*   `ops/`: Scripts `.sh` y `.py` para levantar, migrar y desplegar (Ej. `deploy.sh`). Además contiene los ficheros de entorno (.env).
*   `data/`: Los volúmenes locales persistidos (PostgreSQL) y evidencia/log estáticos (`legacy/code`).

> *Para el plan maestro general de Monstruo y políticas de cumplimiento, consultar los archivos en la raíz del repositorio (`/README.md`, `/ARQUITECTURA.md`).*