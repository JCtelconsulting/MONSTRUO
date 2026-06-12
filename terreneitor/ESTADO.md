# Estado — Terreneitor (módulo del ecosistema)

**Actualizado:** 2026-06-12 · Detalle completo: [docs/MIGRACION_MONSTRUO.md](docs/MIGRACION_MONSTRUO.md)

## Hecho (verificado en navegador)
- **Módulo pleno de Monstruo en DEV**: URL única `terreneitor.telconsulting.cl/dev`
  → hub con tarjetas por rol (Terreno/Supervisión/Gerencia/Administración);
  subdominios viejos redirigen 307. Barra lateral = la REAL del gateway
  (assets vía proxy interno `/shared/*`). Sin login propio: SSO del gateway
  (`MONSTRUO_SSO_SECRET`); login local de respaldo en `/modulos/login/`.
- Contenedor `monstruo-dev-terreneitor:8005` (compose propio
  `terreneitor/docker-compose.yaml`, red `monstruo-dev_default`). El proxy NO
  necesitó cambios (ya apuntaba a 60.8:8005).
- Datos en Postgres central, schema `terreneitor` (migración desde SQLite
  verificada 10/10 tablas; rollback = quitar `TERRENEITOR_DATABASE_URL` del
  `.env` del módulo → vuelve a SQLite local intacto).
- Identidad Premium Gold + logo de fondo (marca de agua) en hub y módulos.
- Funcional: 7 casos de uso de Diego, catálogo de clientes + N° correlativo,
  auto-asignación de técnicos ("Tomar/Crear un trabajo"), QA navegador completo.

## Pendiente
1. **PROD**: replicar Fases 1-2 en la VM 60.5 con ventana y respaldo; resolver
   colisión de cookie `access_token` (ambas apps la usan en `.telconsulting.cl`;
   en dev no choca porque Terreneitor usa `access_token_dev`).
2. Asignar el módulo `terreneitor` en `allowed_modules` a los usuarios que
   corresponda (Configuración→Usuarios; los agentes NO editan auth.users sin OK
   explícito de Juan).
3. Tipografía MADE TOMMY (hoy Dosis como fallback web; faltan los archivos).
4. Autocompletador por audio: scaffold inerte (`backend/services/ia_autocompletador.py`,
   diseño en `docs/AUTOCOMPLETADOR_AUDIO.md`) — requiere faster-whisper + Ollama.

## Operación
- Repo fuente de verdad: `/srv/terreneitor_dev` (GitHub TERRENEITOR, rama `dev`).
  Cambios: commitear allá y sincronizar acá (rsync), o editar acá y portar.
- Tras cambiar el `.env`: `docker compose -f terreneitor/docker-compose.yaml up
  -d --force-recreate` (restart no relee env).
- Usuarios QA: qa.terreno / qa.supervisor / qa.gerencia / qa.dev
  @telconsulting.cl (passwords en memoria del agente o resetear vía portal).
