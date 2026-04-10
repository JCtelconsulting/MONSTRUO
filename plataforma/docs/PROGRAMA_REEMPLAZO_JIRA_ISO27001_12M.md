# PROGRAMA REEMPLAZO JIRA + ISO/IEC 27001 (12 MESES)

Estado: ACTIVO  
Fecha base: 2026-02-15  
Fuente de verdad del programa: este documento

## 1) Objetivo
Reemplazar Jira por la Ticketera MONSTRUO para operación diaria y cerrar certificación ISO/IEC 27001 de alcance completo MONSTRUO, usando la familia 27000 como marco de soporte (27000, 27002, 27005).

## 2) Alcance certificado
- App MONSTRUO y módulos críticos de negocio.
- Integraciones, datos, operación, soporte, cambios, continuidad.
- Proveedores críticos y obligaciones regulatorias aplicables.

## 3) Criterios de éxito
- Jira queda fuera de operación diaria sin degradar SLA ni trazabilidad.
- Operación paralela Jira+MONSTRUO completada por 8 semanas con evidencia diaria.
- Gate Go/No-Go estricto cumplido y acta formal firmada.
- Stage 1 y Stage 2 ISO/IEC 27001 aprobados sin NC mayores abiertas.

## 4) Decisiones cerradas
- Duración paralelo: 8 semanas.
- Estrategia migración: bootstrap inicial de abiertos + delta diario.
- Gate de corte: estricto según Plan Maestro.
- Zona horaria operativa: America/Santiago.

## 5) Cronograma macro (12 meses)
1. Mes 1: Kickoff SGSI, alcance, política, comité y RACI.
2. Mes 2: Inventario de activos, clasificación y matriz de riesgos v1.
3. Mes 3: Cierre técnico EPIC 11 pendiente (adjuntos/historial/worker/runs).
4. Mes 4: Hardening técnico (secretos, logging, backups, trazabilidad).
5. Mes 5: Marco legal/regulatorio y contratos de terceros.
6. Mes 6: Piloto ISO + auditoría interna ciclo 1.
7. Mes 7: Preparación cutover Jira (migración + capacitación).
8. Meses 8-9: Paralelo Jira+MONSTRUO (8 semanas) + control de desviaciones.
9. Mes 10: Go/No-Go, apagado Jira, hypercare 30 días.
10. Mes 11: Auditoría interna ciclo 2 + revisión por dirección.
11. Mes 12: Auditoría externa Stage 1/Stage 2 y cierre de NC menores.

## 6) Fase actual: Paralelo Jira+MONSTRUO (8 semanas)
### Semana 0 - Preparación
- Runbook operativo oficial: `docs/playbooks/paralelo_jira_monstruo.md`.
- Variables Jira por entorno y hardening anti-cruce DEV/PROD.
- Dry-run técnico en DEV con muestra controlada.

### Semana 1 - Bootstrap abiertos
- Import inicial de tickets Jira abiertos.
- Mapa persistente `jira_issue_key -> monstruo_ticket_id`.
- Muestreo funcional de estado/prioridad/comentarios y reconciliación.

### Semanas 2-7 - Operación paralela
- Delta diario Jira -> MONSTRUO idempotente.
- KPI diario comparativo Jira vs MONSTRUO.
- Comité semanal de desvíos con plan de remediación.
- Freeze de cambios no críticos en Ticketera.

### Semana 8 - Cierre y decisión
- Consolidación de evidencia 8 semanas.
- Validación de gate estricto.
- Emisión de acta Go/No-Go.
- Si Go: corte y hypercare 30 días.
- Si No-Go: extensión controlada con backlog y fecha de reevaluación.

## 7) Gate estricto Go/No-Go
- 0 incidentes Sev1 atribuibles a Ticketera durante paralelo.
- >=95% de cumplimiento SLA objetivo en período medido.
- 0 pérdida de trazabilidad Jira/MONSTRUO en muestra auditada.
- Evidencia diaria completa y verificable.
- Acta formal firmada por comité.

## 8) Artefactos y evidencia obligatoria
- `jira_issue_map`, `jira_sync_runs`, `jira_sync_cursor`.
- `parallel_kpi_daily`, `parallel_decisions`.
- Evidencia diaria de reconciliación/KPI.
- Registro de comité semanal y remediaciones.
- Acta final Go/No-Go.

## 9) Gobierno operativo
- Comité SGSI semanal.
- Comité dirección mensual.
- Dueños por dominio: producto, backend, ops, seguridad, legal/compliance.
- Definición de Done por control: implementado + evidenciado + operado.

## 10) Reglas no negociables
- EPIC 11 mantiene prioridad máxima hasta Go/No-Go.
- No desplegar a PROD sin aprobación explícita.
- No mezclar credenciales/tokens/URLs DEV y PROD.
- Ningún cambio sin trazabilidad en Plan Maestro y Proyecto Contexto.
