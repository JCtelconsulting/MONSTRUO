# Scripts Operativos (`code/scripts`)

Esta carpeta concentra utilidades manuales de DB y soporte operacional.

## Estructura canónica

- `debug/`: diagnóstico no destructivo.
- `migrations/`: ajustes de esquema y migraciones manuales.
- `maintenance/`: tareas correctivas de operación (pueden alterar datos).
- `seed/`: datos de prueba o carga inicial controlada.

## Reglas

- No crear scripts sueltos en `code/` ni en `code/scripts/` raíz.
- Todo script nuevo debe vivir en una subcarpeta por tipo.
- Scripts destructivos deben llevar prefijo claro (`purge_`, `reset_`, `reassign_`) y pedir confirmación cuando aplique.
- Los scripts deben ser ejecutables sin `PYTHONPATH` manual (bootstrap interno con `Path`).

## Ejemplos

```bash
python3 code/scripts/debug/check_customers.py
python3 code/scripts/migrations/migrate_system_settings.py
python3 code/scripts/maintenance/reassign_orphan_tickets.py --dry-run
python3 code/scripts/seed/setup_users.py
```
