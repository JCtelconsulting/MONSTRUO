# Escenarios de Demostración - Monstruo

## Escenario 1: Parrotfy Pagos API 500 → Alerta → Recomendación IA → Ticket

### Contexto
El endpoint `/api/v1/payments` de Parrotfy está retornando error 500, bloqueando la sincronización de pagos.

### Flujo Completo

#### 1. Detección Automática (5 min)
```
12:00 - Sync automático ejecuta script sync_parrotfy_payments.py
12:01 - Script recibe HTTP 500 de Parrotfy API
12:01 - Se crea alerta en tabla `alerts`:
        rule: "integration_parrotfy_payments_api_500"
        severity: "high"
        entity_id: "parrotfy_payments"
        summary: "Parrotfy Payments API retorna 500"
```

#### 2. Deduplicación (2 min)
```
12:03 - Script create_parrotfy_workflow_tasks.py ejecuta
12:03 - Fingerprint: "INTEGRATION_ERROR|parrotfy_payments|500"
12:03 - Verifica: ¿Ya existe caso con este fingerprint? NO
12:04 - Crea caso único en workflow:
        Title: "Parrotfy Payments API 500 - Sincronización Bloqueada"
        Priority: "high"
        Assigned: "ops"
```

**Resultado:** 15 alertas idénticas → 1 solo caso

#### 3. Evento al Bridge (1 min)
```
12:05 - Publica evento al Bridge (bridge_messages):
        kind: "workflow_dedupe_result"
        title: "Workflow Dedupe Result - Case 1"
        payload: {"case_id": 1, "created_tasks": 1, "deduped": 15}
```

#### 4. IA Encola Evento (5 min)
```
12:10 - Cron ejecuta enqueue_bridge_events.py cada 5 min
12:10 - Lee bridge_messages desde última ejecución
12:10 - Detecta evento relevante (kind="workflow_dedupe_result", "500" en payload)
12:10 - Inserta en ai_event_queue:
        source: "monstruo_workflow"
        kind: "workflow_dedupe_result"
        payload_json: {...}
        status: "new"
```

#### 5. Worker IA Procesa (10 min)
```
12:20 - Cron ejecuta ai_assistant_worker.py cada 10 min
12:20 - Toma evento status="new" desde ai_event_queue
12:20 - Mapea a playbook: integration_parrotfy_payments_api_500.md
12:20 - Construye prompt: playbook + event data
12:21 - Llama Ollama API (modelo llama3.2):
        POST http://127.0.0.1:11434/api/generate
12:22 - Ollama responde con JSON estructurado:
        {
          "title": "Parrotfy Payments API 500 - Sincronización Bloqueada",
          "summary": "Endpoint /api/v1/payments retorna 500. Problema del lado de Parrotfy.",
          "recommended_actions_internal": [
            "Verificar endpoint directamente con curl",
            "Revisar request IDs en logs",
            "Escalar a soporte Parrotfy si persiste > 24h"
          ],
          "customer_message_draft": "Estimado cliente, hemos detectado..."
        }
12:22 - Guarda en ai_recommendations:
        status: "pending"
        requires_approval: 1
12:22 - Publica al Bridge:
        kind: "ai_recommendation"
12:22 - Agrega comentario en caso workflow
```

#### 6. Aprobación Humana
```
14:00 - Usuario ops abre /ui/asistente.html
14:00 - Ve recomendación PENDIENTE
14:01 - Revisa:
        - Summary: "Endpoint retorna 500..."
        - Actions: 3 acciones sugeridas
        - Customer message draft: borrador listo
14:02 - Click "Aprobar"
14:02 - Estado cambia: pending → approved
14:02 - Audit event registrado
```

#### 7. Ejecución Manual (Opcional)
```
14:05 - Ops sigue acciones recomendadas:
        1. curl https://api.parrotfy.com/api/v1/payments → confirma 500
        2. Revisa logs: extrae request_id
        3. Envía email a soporte Parrotfy con request_id
```

#### 8. Auto-Resolve (24h después)
```
DÍA +1
12:00 - Parrotfy arregla su API
12:30 - Sync automático ejecuta sync_parrotfy_payments.py
12:30 - Respuesta: HTTP 200 OK ✅
12:30 - create_parrotfy_workflow_tasks.py ejecuta
12:30 - Fingerprint "INTEGRATION_ERROR|parrotfy_payments|500" NO aparece
12:30 - miss_streak incrementa: 0 → 1
12:30 - (no auto-close aún, requiere 2+ ciclos)

DÍA +2
12:30 - Fingerprint sigue sin aparecer
12:30 - miss_streak incrementa: 1 → 2
12:30 - AUTO-RESOLVE: marca caso como "done"
12:30 - Agrega comentario: "✅ Auto-resuelto: no reaparece en 2 ciclos"
```

**Timeline total:** Detección →  Ticket → Recomendación IA → Aprobación : ~2 horas  
**Auto-resolve:** +48 horas

---

## Escenario 2: Factura Missing → Ticket Único → Auto-Resolve

### Contexto
Parrotfy tiene 8 facturas que no aparecen en Laudus (recién creadas hace 6 horas).

### Flujo

#### 1. Detección + Deduplicación
```
10:00 - Script compute_parrotfy_discrepancies.py ejecuta
10:00 - Compara Parrotfy vs Laudus
10:00 - Encuentra 8 facturas en Parrotfy sin match en Laudus:
        Folios: 1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008
10:00 - Crea 8 alertas individuales
10:05 - create_parrotfy_workflow_tasks.py ejecuta
10:05 - Fingerprints únicos por folio:
        PF_MISSING_IN_LAUDUS|1001
        PF_MISSING_IN_LAUDUS|1002
        ...
        PF_MISSING_IN_LAUDUS|1008
10:05 - Crea 8 tareas INDIVIDUALES (una por factura)
```

**Nota:** En este caso, NO se deduplican porque cada factura es única.

#### 2. Auto-Categorización por Edad
```
10:05 - Script analiza edad de cada factura:
        - 1001: creada hace 6h → RECIENTE → priority: low
        - 1002: creada hace 6h → RECIENTE → priority: low
        - ...
        - 1008: creada hace 6h → RECIENTE → priority: low
10:05 - Acción sugerida: "Monitor próximo sync (24h)"
```

#### 3. IA Analiza (si hay evento Bridge)
```
10:20 - Worker IA procesa evento
10:20 - Playbook: parrotfy_missing_invoice.md
10:20 - Recomendación:
        "Facturas recientes (<24h). Probable delay de sync.
         Esperar siguiente sincronización antes de escalar."
```

#### 4. Auto-Resolve (32h después)
```
DÍA +1, 18:00 - Laudus sync ejecuta
18:00 - Sincroniza facturas pendientes desde Laudus
18:00 - Facturas 1001-1008 ahora aparecen en Laudus ✅
18:00 - compute_parrotfy_discrepancies.py ejecuta
18:00 - NO encuentra discrepancias (match OK)
18:00 - Fingerprints desaparecen
18:00 - create_parrotfy_workflow_tasks.py ejecuta
18:00 - miss_streak += 1 para cada fingerprint

DÍA +2, 18:00 - Fingerprints siguen sin aparecer
18:00 - miss_streak += 1 (ahora = 2)
18:00 - AUTO-RESOLVE: 8 tareas marcadas como "done"
18:00 - Comentarios: "✅ Auto-resuelto: problema resuelto naturalmente"
```

**Timeline:** Detección → Auto-resolve: ~42 horas  
**Intervención humana:** CERO (todo automático)

---

## Escenario 3: Opt-Out Compliance → Bloqueo Automático

### Contexto
Cliente solicita opt-out de comunicaciones vía email.

### Flujo

#### 1. Solicitud de Opt-Out
```
09:00 - Email recibido: "Solicito cancelar suscripción"
09:10 - Usuario admin abre /ui/crm.html
09:10 - Busca contacto por email: contacto@empresa.com
09:10 - Click "Gestionar Consentimiento"
09:11 - Selecciona: consent_state = "opted_out"
09:11 - Agrega nota: "Solicitado por email 2026-01-24"
09:11 - Click "Guardar"
```

#### 2. Bloqueo Automático
```
09:11 - Sistema ejecuta:
        UPDATE crm_suppression
        SET consent_state = 'opted_out',
            blocked = 1,
            reason = 'customer_request',
            updated_at = '2026-01-24T09:11:00',
            updated_by = 'admin_user'
        WHERE email = 'contacto@empresa.com'
09:11 - Audit event creado:
        event_type: "opt_out_applied"
        details: "contacto@empresa.com opted out by admin_user"
09:11 - Mensaje en UI: "✅ Contacto bloqueado. No se permite contacto futuro."
```

#### 3. Prevención de Contacto
```
10:00 - Script send_marketing_email.py ejecuta (hipotético)
10:00 - Query contacts para email masivo:
        SELECT email FROM contacts
        WHERE active = 1
        AND NOT EXISTS (
            SELECT 1 FROM crm_suppression
            WHERE crm_suppression.email = contacts.email
            AND blocked = 1
        )
10:00 - contacto@empresa.com NO aparece en lista ✅
```

**Compliance**: 100% automático, 0 violaciones

#### 4. Auditoría Completa
```sql
-- Ver historial completo
SELECT 
  consent_state, blocked, reason,
  updated_at, updated_by, notes
FROM crm_suppression
WHERE email = 'contacto@empresa.com'
ORDER BY updated_at DESC;

-- Resultado:
-- opted_out | 1 | customer_request | 2026-01-24 09:11 | admin_user | "Solicitado por email..."
```

---

## Comparación: Antes vs Después

| Escenario | Antes de Monstruo | Después de Monstruo |
|-----------|-------------------|---------------------|
| **Parrotfy 500** | 15 tickets diferentes, cada uno diagnosticado manualmente (~30h total) | 1 ticket, IA sugiere diagnóstico en 10 min, auto-resolve en 48h |
| **Factura missing** | Alertas ignoradas o investigadas manualmente una por una (~16h) | Auto-categorización + auto-resolve (~0h intervención) |
| **Opt-out** | Email manual a lista, riesgo de error humano | Bloqueo automático 100%, auditoría completa |

**Ahorro estimado:** ~45 horas/semana para equipo de 3 personas

---

**Última actualización**: 2026-01-24  
**Propietario**: Equipo Monstruo
