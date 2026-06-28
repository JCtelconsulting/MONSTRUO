# Seguridad de las aplicaciones — estado y decisiones

> Origen: auditoría de seguridad de aplicaciones del **2026-06-28** (revisión multi-agente con
> verificación adversarial de explotabilidad). Este documento resume **qué se arregló**, **qué
> queda** y **las decisiones de diseño**, para que cualquier agente/persona retome con contexto.
> Complementa [INFRAESTRUCTURA_HARDENING.md](INFRAESTRUCTURA_HARDENING.md) (infra/VMs/firewall).

## Resumen

La plataforma central (gateway / core / ticketera / gta) está **bien construida**: queries
parametrizadas (sin SQL injection), JWT HS256, cookies `HttpOnly + SameSite=Lax + Secure`,
bcrypt, y *fail-closed* de `SECRET_KEY` débil en prod. Los huecos encontrados eran de
**autorización fina** (scope por área incompleto en escritura) y **operación de sesión**
(sin rate-limit, sin revocación). El riesgo más concentrado estaba en **terreneitor** (auth
propia, menos madura). Todo lo explotable se aplicó en `dev` el 2026-06-28.

## Arquitectura relevante

- **Fundación se separó a su propio stack**: el código vivo está en **`/srv/fundacion_dev`**
  (repo git propio, rama `master`, dominio `fundacion.telconsulting.cl`, puerto 9006, DB y
  login propios). El directorio `/srv/monstruo_dev/fundacion/` es **LEGACY/duplicado** — no se
  construye ni se sirve; no editarlo.
- **Aislamiento por módulo** es regla de oro: la única base común es el login del gateway.

## Lo aplicado (dev, 2026-06-28)

### Bloque 1 — alto/crítico
| ID | Módulo | Fix | Commit |
|----|--------|-----|--------|
| LEAK-01 | terreneitor | `/api/common/view` exige sesión (era anónimo desde Internet) | 1673c0c |
| SECRET-01 | terreneitor | Contraseñas fuera del código (seed por env/aleatorio) | 1673c0c |
| FILE-01 | terreneitor | `/api/admin/files/view` confinado a `BASE_FILES_DIR` | 1673c0c |
| DEP-02 | terreneitor | python-multipart 0.0.9 → 0.0.18 (CVE-2024-53981) | 1673c0c |
| AUTHN-01 | gateway | Rate-limit en el login (10/5min → 429) | 6fdda60 |
| AUTHN-02 | core | Revalida `is_active` por request (revocación inmediata, fail-open) | ae9aaaf |
| LEAK-02 | gta | Scope por área en `GET /solicitudes/{sid}` | 2e0af6d |

### Bloque 2/3 — medio + hardening
| ID | Módulo | Fix | Commit |
|----|--------|-----|--------|
| AUTHZ-01 | gta | 6 endpoints de escritura `gta:read` → `gta:write` | ff6f370 |
| LEAK-06 | gta | Errores 500 sin `str(e)` | ff6f370 |
| GTA-SECRET-01 | gta | Guard fail-closed de `SECRET_KEY` débil | 13c73aa |
| AUTHZ-04 | terreneitor | CRUD de clientes exige `require_gestion` (no TERRENO) | e6ea633 |
| LEAK-04 | terreneitor | Descargas de informes (IDOR) exigen `require_gestion` | e6ea633 |
| AUTHN-05 | terreneitor | Password mínimo 4 → 8 | e6ea633 |
| FILE-02 | terreneitor | Allowlist de subidas (imágenes + PDF) | e6ea633 |
| CORS-01 | terreneitor | Fuera `localhost` de orígenes permitidos | e6ea633 |
| LEAK-03 | ticketera | Scope por área en `/directorio/tickets` | f160d93 |
| AUTHN-03 | gateway | El login ya no devuelve el JWT en el body JSON | b0ce5a6 |
| AUTHN-04 | gateway | `max_age` de cookie alineado al exp del JWT (era 12h muerta) | b0ce5a6 |
| LEAK-07 | gateway | `GET /api/sesion` sin `str(exc)` (+ log server-side) | b0ce5a6 |
| AUTHZ-02 | **fundacion** | `PATCH /tareas/{id}` `:read` → `:write` | 0b1ec45 *(repo fundacion_dev)* |
| LEAK-05 | **fundacion** | 7 errores 500 sin `str(e)/str(exc)` | 0b1ec45 *(repo fundacion_dev)* |
| FUND-SECRET-01 | **fundacion** | Guard fail-closed de `SECRET_KEY` (firma sus propios JWT) | 0b1ec45 *(repo fundacion_dev)* |

Verificado: tests OK (gateway 21, gta 18, terreneitor 21, ticketera 21, fundacion 12), las apps
healthy, LEAK-01 confirmado funcionalmente (401 sin sesión).

### Cierre tras revisión adversarial (10 agentes)

Una revisión adversarial multi-agente sobre todos los fixes encontró **2 huecos reales** que los
parches iniciales no cerraban (ruta paralela / endpoint hermano), ya corregidos:

| Hallazgo | Sev | Fix | Commit |
|----------|-----|-----|--------|
| `/api/gerencia/*` (informes + KPIs) exigía solo `require_session` → TERRENO accedía por ruta paralela a download-job/-direct | **alta** | todo el router `/api/gerencia` → `require_gestion` | db00487 |
| `/directorio/metricas` y `/directorio/clientes` agregaban datos de otras áreas | media | scope por área en ambos (como `/directorio/tickets`) | 9eec339 |
| rate-limiter de login dejaba claves muertas en memoria | baja | limpieza de claves vacías | 70c99b7 |
| `/api/sesion` (fundación) filtraba `str(exc)`; alta de usuario admin sin política de password | baja | detalle genérico + `password>=8` | 3f66275, db00487 |

Falso positivo descartado por verificación: FILE-02 "pierde fotos offline" — el flujo preserva el
nombre de archivo; solo afectaría a videos (UX, no seguridad).

## Decisiones de diseño

- **CSRF-01 — NO se implementaron tokens CSRF.** Las cookies de sesión de los 4 servicios
  (gateway, ticketera, fundacion, terreneitor) ya usan `SameSite=Lax + HttpOnly + Secure`, lo que
  bloquea el envío de la cookie en POST cross-site — el vector CSRF clásico queda mitigado.
  Implementar doble-submit/sincronizado obligaría a tocar todos los forms/fetch de 4 frontends y
  sus backends, con alto riesgo de romper flujos en producción por beneficio incremental bajo.
  Si en el futuro se quisiera endurecer sin tokens, el camino menos invasivo es exigir un header
  `X-Requested-With` en las rutas que mutan.
- **XSS-01 (ticketera) — ya cubierto.** El frontend escapa los datos de usuario con
  `TksUI.escapeHtml`; los `innerHTML` sin escape solo interpolan `e.message` y contadores. No se
  añadió DOMPurify (invasivo, sin beneficio real).
- **`require_gestion` (terreneitor)** = ADMIN/GERENCIA/SUPERVISOR (no TERRENO), para gestión de
  catálogos y descarga de informes.

## Pendiente

1. **Deploy a PROD** — todo está en `dev` (monstruo) y `master` (fundacion_dev). El deploy lo
   centraliza **una sola sesión** para evitar choques de `docker compose` entre sesiones paralelas.
2. **AUTHZ-03 ticketera** (validar área al *tomar*/editar tickets) — **delicado**: los roles
   `ops`/`implementaciones` mapean a "general"/`SIN_AREA` con scope `[]`; un check ingenuo los
   dejaría sin poder tomar ningún ticket. Requiere sesión dedicada con tests del flujo. Ticketera
   está en producción.
3. **LEAK-02 en tareas de gta** (`/tareas/{id}`, `/tareas/subarea/{n}`, `/tareas/bandeja`) y
   **VALID-01** (body:dict → Pydantic) — usan el modelo de membresías, más delicados.
4. **Rotar las claves restantes** de usuarios de terreneitor en prod (casi todas ya cambiadas).
5. **Limpieza opcional** (bajo riesgo, commits aparte): quitar `fundacion_ui_dir` muerta en
   gateway, las `location /dev/api/fundacion` + upstreams de `monstruo.conf`, y el dir legacy
   `/srv/monstruo_dev/fundacion/`.
