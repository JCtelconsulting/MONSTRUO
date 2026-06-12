# Handover Técnico - Terreneitor v3.0

Este documento está dirigido al desarrollador (humano o IA) que asuma la continuidad de Terreneitor.

## 1. Arquitectura del Sistema
El sistema sigue un patrón de **Backend Monolítico Modular** con un **Frontend Desacoplado** en JS Vanilla.

- **Backend**: Python FastAPI.
- **Punto de Entrada**: `code/sistema_gestion/cerebro.py` (Carga rutas y middleware).
- **Core Lógico**: `code/sistema_gestion/nucleo.py` (Configuración de base de datos y utilidades críticas).
- **Frontend**: Localizado en `code/static/modulos/`. Cada módulo es independiente (HTML/JS/CSS).

## 2. Gestión de Base de Datos (Multi-Tenant)
Terreneitor utiliza una arquitectura de **Base de Datos por Cliente (SQLite)**.
- El archivo `nucleo.py` resuelve el motor de base de datos basándose en el subdominio o el encabezado `x-forwarded-host`.
- **Ubicación**: `data/db/*.db`.
- **Migraciones**: Se utiliza **Alembic**. Siempre que se modifique `modelos.py`, se debe generar una migración:
  ```bash
  alembic revision --autogenerate -m "descripcion"
  alembic upgrade head
  ```

## 3. Manejo de Entornos (Dev/Prod)
El sistema está diseñado para correr en paralelo:
- **Producción**: Puerto 8080.
- **Desarrollo**: Puerto 8081.
- El proxy inverso (Nginx) inyecta el prefijo `/dev` o `/prod`. El middleware `EnvPathPrefixMiddleware` en `nucleo.py` se encarga de striptear este prefijo para que el código interno no se vea afectado.

## 4. Flujo de Trabajo con IA (Best Practices)
Este proyecto fue desarrollado en su totalidad mediante Pair Programming con IA. Para mantener la coherencia:
- **Contexto**: Antes de editar, lea siempre `docs/PLAN_MAESTRO.md` y `docs/PROYECTO_CONTEXTO.md`.
- **Modularidad**: Si agrega una nueva funcionalidad, cree un archivo `rutas_nueva_funcion.py` y regístrelo en `cerebro.py`.
- **UI/UX**: Mantenga el estándar "Dark Mode" y el uso de la fuente *Space Grotesk*. No use frameworks de CSS pesados si no es estrictamente necesario.

## 5. Mantenimiento y Scripts
La carpeta `ops/scripts/` contiene herramientas vitales:
- `backup/`: Gestión de respaldos externos.
- `mantenimiento/`: Limpieza de logs y temporales.
- `crear_estructura/`: Script para generar la jerarquía de carpetas requerida por los proyectos PMC/SATLINK/etc.

## 6. Advertencias Técnicas
- **EXIF**: La validación de fotos depende de los metadatos EXIF. Si las fotos se pierden o se corrompen, el sistema las moverá a "Cuarentena".
- **PWA**: El `service-worker.js` en la raíz de `static` gestiona el cache. Al subir cambios a JS/CSS, aumente la versión en los archivos `.html` (query param `?v=XX`) para forzar la actualización en los clientes.
