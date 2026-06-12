# Validación E2E Ticketera - DEV
**Fecha:** dom 15 feb 2026 14:59:57 -03
**Commit:** 11b556f

## Ejecución de Pruebas

### 1. verify_hardening.py
```
[OK] Hardening repo PASS
[SUCCESS] verify_hardening PASS
[PASS] verify_hardening.py
```

### 2. verify_hardening.py --check-api
```
[OK] Hardening repo PASS
[OK] Hardening API PASS
[SUCCESS] verify_hardening PASS
[PASS] verify_hardening.py --check-api
```

### 3. e2e_api_full.py
```
[OK] Login: juan.lopez@telconsulting.cl
[OK] whoami
[OK] Ticket creado: TK-15-02-2026-0004 (id=4)
[OK] Detalle ticket
[OK] Evento agregado
[OK] Timeline con 2 eventos
[OK] Estado actualizado a en_progreso
[OK] Stats
[OK] Listado filtrado
[SUCCESS] E2E API full PASS
[PASS] e2e_api_full.py
```

### 4. e2e_ticketera.py (Incoming Match)
```
[OK] Login: juan.lopez@telconsulting.cl
[OK] Tickets creados: inc=5 req=6 chg=7
[OK] Idempotencia transición activa
[OK] Bloqueo de ejecución sin doble aprobación
[OK] Workflow + doble aprobación validado
[OK] Dedupe de correo activo
[OK] Reply + dedupe + incoming thread match + download adjuntos validados
[OK] Auto-reply seguro validado (allowlist + antiloop + one-shot)
[OK] Contrato SLA metrics/breaches validado
[OK] Compliance core validado (incluye rerun cuando falta artefacto)
[OK] Worker canales: sin usuario con phone_number, test de dispatch omitido en este entorno
[OK] Cola jobs validada (queue-health + recover stale + dedupe recurrentes)
[OK] Paralelo Jira+MONSTRUO técnico validado (bootstrap/delta/runs/kpi/go-no-go)
[SUCCESS] E2E Ticketera PASS
[PASS] e2e_ticketera.py
```
