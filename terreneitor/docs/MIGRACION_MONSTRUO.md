# Migración: Terreneitor como módulo de Monstruo

> Estado 2026-06-12: **Fases 1, 2 y 3 (SSO) COMPLETAS en DEV**. PROD intacto.

## Por qué

Juan mantiene dos apps (Monstruo y Terreneitor) con dos auth, dos bases, dos
deploys. Decisión: Terreneitor pasa a ser un módulo más de Monstruo ("una sola
app con hartos módulos"), por etapas reversibles.

## Fase 1 — Módulo con contenedor propio ✅

- Código en `/srv/monstruo_dev/terreneitor/` (copia rsync del repo
  `/srv/terreneitor_dev`, sin `.git`; la historia git sigue viviendo allá).
- Servicio `terreneitor` en el `docker-compose.yaml` raíz (compose único) →
  contenedor `monstruo-dev-terreneitor`, puerto host **8005** (el proxy 60.6 ya
  ruteaba los dominios de terreneitor dev a 60.8:8005 → **cero cambios de proxy**).
- Red externa `monstruo-dev_default` → ve el Postgres central como `db:5432`.
- El contenedor viejo `terreneitor-app-dev` quedó apagado; `/srv/terreneitor_dev`
  queda como respaldo + fuente de verdad git.
- El servicio ya quedó plegado en el `docker-compose.yaml` raíz de monstruo
  (compose único). El bloque real es:

```yaml
  terreneitor:
    build: { context: ./terreneitor, dockerfile: docker/Dockerfile }
    container_name: monstruo-dev-terreneitor
    ports: ["8005:8000"]
    volumes:
      - ./terreneitor/backend:/app/backend
      - ./terreneitor/frontend:/app/frontend
      - ./terreneitor/data:/app/data
      - ./terreneitor/logs:/app/logs
    env_file: [./terreneitor/ops/environments/.env]
    environment: [PYTHONUNBUFFERED=1, ENV=dev]
    user: "1000:1000"
    restart: unless-stopped
    depends_on: [db]
```

## Fase 2 — SQLite → Postgres central ✅

- Backend: `TERRENEITOR_DATABASE_URL` (commit `0a97d49`); si está seteada usa un
  engine único Postgres, si no, SQLite multi-tenant como siempre. El listener de
  PRAGMA quedó blindado a SQLite. Driver `psycopg2-binary`.
- Datos en schema **`terreneitor`** de la DB `monstruo_dev` (convención schema
  por módulo). Migración con `ops/scripts/migracion/sqlite_a_postgres.py`
  (tablas desde modelos + datos con IDs + secuencias + verificación): **PASS**,
  10/10 tablas con conteos idénticos.
- La URL (con `search_path=terreneitor,public`) vive en
  `terreneitor/ops/environments/.env` (no commiteado). OJO: tras cambiar el
  `.env`, `docker compose up -d --force-recreate` (restart no relee env).
- Fixes de portabilidad encontrados con la app corriendo en PG (commit `476dbc6`):
  - `strftime('%s')` → `EXTRACT(EPOCH ...)` en PG (duración SLA).
  - Productividad semanal/mensual: agrupación movida a Python.
  - `func.date()` en PG devuelve `date` (no str) → normalizar claves `str(...)`.
- **Verificación E2E sobre Postgres** (navegador, vía proxy): supervisor,
  terreno (planes/tareas) y gerencia (KPIs) con 0 errores 5xx/consola y 0
  imágenes rotas; escritura probada (INSERT cliente con secuencia OK).

### Rollback Fase 2
Quitar `TERRENEITOR_DATABASE_URL` del `.env` y `up -d --force-recreate` →
vuelve al SQLite local (quedó intacto). Rollback total: levantar el compose
viejo en `/srv/terreneitor_dev/docker/docker-compose.dev.yml`.

## Fase 3 — SSO con el gateway ✅ (implementado en DEV)

Un solo login para el ecosistema: la sesión del gateway de Monstruo sirve para
entrar a Terreneitor sin segundo login (commit `f8831e9` en repo terreneitor).

- **Terreneitor acepta el JWT del gateway**: `_session_desde_gateway()` en
  `backend/core/dependencias.py`. Valida la cookie `access_token` con
  `MONSTRUO_SSO_SECRET` (la SECRET_KEY del stack, en el `.env` del módulo),
  autoriza contra `auth.users` del Postgres compartido (requiere
  `"terreneitor"` en `allowed_modules`, o rol `admin`) y auto-provisiona un
  usuario espejo local. Mapeo de roles gateway→local: admin/sistemas→ADMIN,
  gerencia→GERENCIA, ops/supervisor→SUPERVISOR, terreno→TERRENO.
- **Módulo registrado en Monstruo**: `UI_MODULES` + `PERMISSION_TO_MODULE_MAP`
  (`plataforma/core/config.py`), tile en `gateway/.../sidebar.js`
  (prod: `terreneitor.telconsulting.cl`, local: `:8005`) y opción en la UI de
  Configuración→Usuarios (`users_ui.js`) para asignar el módulo.
- **Vuelta al ecosistema**: los 4 sidebars de Terreneitor tienen link "Monstruo"
  al dashboard del gateway.
- El login propio de Terreneitor sigue funcionando (usuarios QA / fallback).
  Sin `MONSTRUO_SSO_SECRET` el SSO queda inerte (modo standalone).
- **Verificado en navegador**: con sesión del gateway → Terreneitor abre sin
  pedir login; whoami devuelve `sso: "monstruo"`; usuario espejo creado.

### Pendiente de la Fase 3
- **Asignar el módulo a los usuarios** (lo hace Juan en Configuración→Usuarios
  del gateway, o SQL: agregar `"terreneitor"` a `allowed_modules`). Sin eso el
  tile no aparece y el SSO rechaza (salvo rol admin).
- Para PROD: resolver la colisión de cookie `access_token` (ambas apps la usan
  en `.telconsulting.cl`; en dev no choca porque Terreneitor usa
  `access_token_dev`). Opción recomendada: al promover, Terreneitor deja de
  emitir su cookie y vive solo del SSO.
- Apagar (opcional) el login propio + Google OAuth propio cuando todos los
  usuarios estén en `auth.users`.

## Pendientes

- [x] Plegar el servicio al `docker-compose.yaml` raíz y commitear `terreneitor/`
      en el repo monstruo. **Hecho** (2026-06-12); compose único.
- [ ] Fase 3 SSO (diseño arriba).
- [ ] PROD: repetir Fases 1-2 en 60.5 (con ventana y respaldo), actualizar
      `terreneitor.conf` del proxy si cambia el backend, y recién ahí retirar
      el stack viejo.
- [ ] Monitoreo Zabbix del healthcheck `/health` del módulo (EPIC 14).
