# EPICs futuros / no implementados

Snapshot de los EPICs que estaban especificados en `GUIA_MAESTRA.md` (versión `archive/GUIA_MAESTRA_v1_2026-02.md`) pero nunca se ejecutaron, o quedaron deprioritizados por enfoque en GTA + ticketera + módulos productivos.

Se conservan como referencia para futura priorización. Si alguno se reactiva, mover su contenido a la `GUIA_MAESTRA.md` activa con estado actualizado.

> Estado a 2026-05-05: ninguno de estos EPICs está activo ni en roadmap inmediato.


---

## EPIC 14 — Zabbix → Ticket

EPIC 14 — Zabbix → Ticket (Anteriormente 13)

Tareas:
- webhook receiver
- dedupe y agregación
- incidente mayor
- notificaciones

Aceptación:
- alerta alta crea ticket/incidente


---

---

## EPIC 15 — Preventa configurador + proveedores

EPIC 15 — Preventa configurador + proveedores

Tareas:
- plantillas
- formularios dinámicos
- motor reglas de alcance
- scoring proveedores
- comparador

Aceptación:
- propuesta consistente con alcance


---

---

## EPIC 16 — Reporting

EPIC 16 — Reporting

Tareas:
- dashboards gerencia
- export
- reportes cliente
- snapshots mensuales

Aceptación:
- reportes reproducibles y auditables


---

---

## EPIC 22 — Flujo Proyecto a Caja (Project-to-Cash)

EPIC 22 — Flujo Proyecto a Caja (Project-to-Cash) [PENDIENTE]

**Objetivo:** Vincular el avance de Proyectos (PMO) con la Facturación, alertando a Finanzas cuando se cumplen hitos facturables.

Tareas:
- [ ] Integración entre módulos: PMO -> Finanzas (Trigger por Hito Completado)
- [ ] Dashboard Finanzas: Widget "Proyectos listos para facturar"
- [ ] Flujo de Validación: JP marca hito -> Finanzas aprueba y emite DTE
- [ ] Trazabilidad de Ingresos: Link directo entre Factura y Hito de Proyecto

Aceptación:
- [ ] Finanzas tiene visibilidad proactiva de hitos completados sin intervención manual
- [ ] Cada factura emitida tiene rastro del hito técnico que la originó

---

---

## EPIC 23 — Sincronización Comercial Unificada

EPIC 23 — Sincronización Comercial Unificada [PENDIENTE]

**Objetivo:** Evitar desajustes de información entre Área Comercial (CRM) y Operaciones/Finanzas asegurando un "Single Source of Truth".

Tareas:
- [ ] Definir Ficha Maestra del Cliente en CRM (Campos mandatorios para Facturación)
- [ ] Propagation Job: Sincronización CRM -> Laudus / Parrotfy / Ticketera
- [ ] Auditoría de cambios en datos críticos (Razón Social, RUT, Dirección de Facturación)
- [ ] Interfaz de validación de discrepancias de contacto comercial vs facturación

Aceptación:
- [ ] Los cambios en el CRM se propagan automáticamente a los sistemas satélites en < 5 min
- [ ] El flujo de facturación no se bloquea por falta de datos mandatarios (validados en CRM)

