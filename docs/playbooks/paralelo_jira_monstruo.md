# Playbook Operativo: Paralelo Jira + MONSTRUO

Estado: Vigente  
Entorno objetivo: Operación productiva controlada (DEV solo dry-run)

## 1) Objetivo
Ejecutar paralelo Jira+MONSTRUO durante 8 semanas con sincronización controlada, reconciliación diaria, KPI comparativo y decisión formal Go/No-Go.

## 2) Prechecks obligatorios
- Rama `dev` limpia y sincronizada.
- `docs/PROGRAMA_REEMPLAZO_JIRA_ISO27001_12M.md` vigente.
- Variables de entorno Jira definidas por entorno.
- Verificación hardening anti-cruce DEV/PROD en verde.

## 3) Variables requeridas
- `JIRA_BASE_URL`
- `JIRA_USER`
- `JIRA_API_TOKEN`
- `JIRA_PROJECT_KEYS`
- `JIRA_SYNC_ENABLED`
- `JIRA_SYNC_DAILY_HOUR`
- `JIRA_SYNC_TZ`

## 4) Endpoints operativos
- `POST /api/tks/migration/jira/bootstrap-open`
- `POST /api/tks/migration/jira/delta-sync/run`
- `GET /api/tks/migration/jira/runs`
- `GET /api/tks/migration/jira/reconciliation/daily`
- `GET /api/tks/parallel/kpi/daily?from=&to=`
- `POST /api/tks/parallel/go-no-go`

Permiso requerido: `tickets:compliance`.

## 5) Semana 0 (dry-run DEV)
1. Ejecutar bootstrap con `dry_run=true` y muestra acotada.
2. Ejecutar delta manual dos veces seguidas para validar idempotencia.
3. Validar `runs` y reconciliación diaria.
4. Confirmar snapshot KPI diario.

## 6) Semana 1 (bootstrap real)
1. Ejecutar bootstrap de tickets abiertos (sin dry-run).
2. Verificar tabla de mapeo Jira->MONSTRUO.
3. Muestrear casos de comentarios, prioridades y estados.
4. Registrar evidencia diaria.

## 7) Semanas 2-7 (operación diaria)
1. Ejecutar delta diario automático (`JIRA_DELTA_SYNC_DAILY`) y monitorear runs.
2. Publicar KPI diario comparado con corte de severidad/SLA/aging.
3. Ejecutar reconciliación diaria y abrir remediaciones si hay mismatch.
4. Escalar al comité semanal cualquier desviación.

## 8) Manejo de fallos
- Si Jira API falla:
  - run queda `failed` o `completed_with_errors`.
  - no debe impactar API principal de Ticketera.
  - registrar evidencia y alerta operativa.
- Si hay mismatch:
  - identificar `jira_issue_key` afectado.
  - aplicar delta manual correctivo.
  - registrar resultado en evidencia diaria.

## 9) Semana 8 (cierre)
1. Consolidar evidencia de 8 semanas.
2. Evaluar gate estricto:
   - 0 Sev1 Ticketera.
   - >=95% SLA.
   - 0 pérdida de trazabilidad auditada.
3. Registrar decisión en `POST /api/tks/parallel/go-no-go`.
4. Si `go`: ejecutar plan de corte + hypercare 30 días.
5. Si `no_go`: definir backlog de brechas y nueva fecha de revisión.

## 10) Evidencia mínima diaria
- Resultado `jira_sync_runs` del día.
- Snapshot `parallel_kpi_daily` del día.
- Resultado `reconciliation/daily`.
- Incidentes/desviaciones y acciones correctivas.
- Firma operativa del responsable del día.
