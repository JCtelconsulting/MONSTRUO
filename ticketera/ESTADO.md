# Estado — Ticketera (EPIC 11, prioridad de negocio)

**Actualizado:** 2026-06-12

## Hecho (verificado)
- Hotfix IMAP integrado en `dev`: lectura por cursor UID con BODY.PEEK, tabla
  `processed_email_messages`, dedupe por Message-ID, `MAIL_SANDBOX` como
  kill-switch absoluto (dev nunca manda correo real).
- **Auto-respuesta (acuse de recibo) SIEMPRE activa**: se retiró el toggle de
  Configuración y el camino de apagado en backend (decisión de Juan 2026-06-12).
  Protecciones vigentes: sandbox, allowlist de destinatarios, idempotencia.
- Tiempos de Configuración→Ticketera **verificados como reales**: ciclo de
  lectura re-agenda el job (30–1800s), delay de auto-respuesta agenda el envío
  (0–1440 min), auto-cierre cierra resueltos tras N horas (job, default 24).
  Se leen de `system_settings` en cada ciclo (sin reinicio).
- Jobs sanos: EMAIL_POLLING / TKS_SLA_EVALUATE / RECOVER_STALE_JOBS completando.
  (Las fallas "Unknown Handler" del dashboard eran de las 3 semanas que gateway
  y ticketera estuvieron caídos — contenedores con mounts viejos, recreados el
  2026-06-12.)

## Pendiente
1. **Casilla real en dev**: imap/smtp vacíos en Configuración → configurar una
   casilla de prueba para validar correo E2E.
2. Suite E2E ticketera en verde (create → reply → dedupe → incoming thread match).
3. Criterios Go/No-Go (PLAN_MAESTRO §0.6): 0 errores 500 en flujos críticos,
   correo completo (hilo+adjuntos+historial), anti-dup, separación DEV/PROD,
   UX fluida, cierre del paralelo Jira (endpoint de decisión ya existe).
4. ⚠️ El refactor de `service.py` a package (`backend/services/service/`) está
   en la **rama archivada**, no en dev — se recupera con el merge pendiente
   (ver PROYECTO_CONTEXTO, decisión #1). El fix "auto-reply siempre activa" de
   dev habrá que re-aplicarlo en `_email.py::should_schedule_auto_reply` al
   fusionar.
