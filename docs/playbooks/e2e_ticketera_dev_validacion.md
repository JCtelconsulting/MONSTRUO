# Validación E2E Ticketera - DEV
**Fecha:** sáb 14 feb 2026 19:31:26 -03
**Commit:** b8d8b8e

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
[OK] Ticket creado: TK-14-02-2026-0034 (id=34)
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
[OK] Ticket creado: TK-14-02-2026-0035 (id=35)
[OK] Primer reply enviado
[OK] Dedupe activo: Se evitó un envío duplicado (correo ya enviado recientemente).
[INFO] Thread ID capturado: mock-1771108289@monstruo.dev
[INFO] Ejecutando simulación de correo entrante en contenedor API...
[OK] Simulación incoming ejecutada.
[OK] Incoming Thread Match VERIFICADO (Correo entrante apareció en el historial).
[OK] Historial validado (Outgoing + Incoming). Correos totales: 2
[SUCCESS] E2E Ticketera PASS
[PASS] e2e_ticketera.py
```
