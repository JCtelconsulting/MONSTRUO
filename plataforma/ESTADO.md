# Estado — Plataforma / Gateway (shell del ecosistema)

**Actualizado:** 2026-06-12

## Hecho (verificado en navegador)
- **SSO del ecosistema**: gateway emite JWT (cookie `access_token`,
  `.telconsulting.cl`); Terreneitor lo acepta (módulo registrado en
  `UI_MODULES`/`PERMISSION_TO_MODULE_MAP`/`sidebar.js`/`users_ui.js`).
- **Identidad Premium Gold** en la shell (`monstruo.css` + login del gateway):
  dorado #D4A843 sobre #050505 + marca de agua del cubo en todos los módulos
  (logo completo en el login). Reglas: [docs/design.md](docs/design.md) +
  [docs/manual-marca-telconsulting.md](docs/manual-marca-telconsulting.md).
- **Dashboard = lanzadera**: solo tarjetas por módulo filtradas por permisos
  (KPIs centralizados retirados a propósito — cada app tiene sus reportes;
  decisión Juan 2026-06-12).
- **Configuración**: pestaña Ticketera sin nota de plantillas ni toggle de
  acuse; usuarios todos eliminables salvo la sesión propia (backend también lo
  bloquea); permisos como 2 acordeones compactos alineados.
- Gateway y ticketera recreados 2026-06-12 (estuvieron 3 semanas caídos por
  mounts viejos tras un refactor).

## Pendiente
1. El frontend del gateway divergió de la línea archivada (botones canónicos,
   tipografía clamp, KPIs por app) — se reconcilia en el merge (decisión #1).
2. Roles finos para Terreneitor en RBAC (`terreno`, `supervisor_terreno`) si se
   quiere más granularidad que `allowed_modules`.
3. Limpiar fallas históricas de jobs si el dashboard de estado siguiera
   mostrando DEGRADED (eran de la caída de 3 semanas).
