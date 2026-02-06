# Playbook: Error 500 en API de Pagos Parrotfy

## Contexto

El endpoint de pagos de Parrotfy (`/api/v1/payments`) está retornando **HTTP 500 Internal Server Error** de manera consistente, bloqueando la sincronización de datos de pagos.

## Síntomas

- ❌ Sincronización de pagos falla con error 500
- ⚠️ Facturas y productos se sincronizan correctamente
- 📊 Sin pagos actualizados en últimas X horas
- 🔴 Alerta: `integration_parrotfy_payments_api_500`

## Diagnóstico Probable

1. **Problema del lado de Parrotfy (90% probabilidad)**
   - Servicio caído temporalmente
   - Mantenimiento programado no comunicado
   - Bug en versión reciente de su API

2. **Problema de autenticación (5%)**
   - Token expirado o revocado
   - Cambio en headers requeridos

3. **Problema de rate limiting (3%)**
   - Excedimos límite de requests
   - IP bloqueada temporalmente

4. **Problema de datos (2%)**
   - Payload inválido en request
   - Cambio en schema esperado

## Checklist de Verificación

### Paso 1: Verificar Estado del Servicio
```bash
# Probar endpoint directamente
curl -X GET "https://api.parrotfy.com/api/v1/payments" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "X-Parrotfy-Store: staging"

# Revisar headers de respuesta
curl -I "https://api.parrotfy.com/api/v1/payments" \
  -H "Authorization: Bearer <TOKEN>"
```

**Resultado esperado:**
- ✅ 200 OK → Problema resuelto
- ❌ 500 → Confirma problema en Parrotfy
- 401 → Problema de autenticación
- 429 → Rate limiting

### Paso 2: Revisar Request IDs
```sql
SELECT rule, summary, details_json, first_seen_at, last_seen_at
FROM alerts
WHERE rule = 'integration_parrotfy_payments_api_500'
ORDER BY last_seen_at DESC LIMIT 5;
```

Extraer `request_id` de `details_json` para escalar a soporte Parrotfy.

### Paso 3: Verificar Otros Endpoints
```bash
# Probar invoices (debería funcionar)
curl "https://api.parrotfy.com/api/v1/invoices" -H "Authorization: Bearer <TOKEN>"

# Probar inventory (debería funcionar)
curl "https://api.parrotfy.com/api/v1/inventory" -H "Authorization: Bearer <TOKEN>"
```

**Si solo `/payments` falla → confirma problema específico de ese endpoint**

### Paso 4: Revisar Evidencia Local
```bash
# Ver logs de sync
tail -100 /srv/monstruo/data/logs/sync_parrotfy_payments.log

# Ver intentos recientes
sqlite3 /srv/monstruo/data/db/monstruo.db \
  "SELECT * FROM import_runs WHERE source='parrotfy_payments' ORDER BY started_at DESC LIMIT 5;"
```

## Riesgos e Impacto

### Alto Riesgo
- **Gap de datos de pagos**: No se actualizan pagos durante la caída
- **Discrepancias no detectadas**: Problemas de conciliación no visibles

### Medio Riesgo
- **Retrasos en reportes**: Dashboards desactualizados
- **Esfuerzo manual**: Equipo finance debe verificar manualmente

### Bajo Riesgo
- **Integridad DB**: No afecta datos ya sincronizados
- **Otros módulos**: Facturas e inventario funcionan normal

## Acción Interna Sugerida (Solo Workflow)

### 1. Crear Ticket Interno
- **Título**: `Parrotfy Payments API 500 - Sincronización Bloqueada`
- **Prioridad**: Alta
- **Asignado a**: Finance + Ops
- **Descripción**: 
  ```
  Endpoint /api/v1/payments retorna 500.
  Request IDs: <LISTA>
  Última sincronización exitosa: <TIMESTAMP>
  Facturas e inventario funcionan OK.
  ```

### 2. Marcar Sync como SKIP Temporal
```python
# En sync_parrotfy_payments.py
if response.status_code == 500:
    log.warning("Parrotfy payments API retorna 500, skipping sync")
    # NO fallar el job completo, solo skipear pagos
    return {"status": "skipped", "reason": "api_500"}
```

### 3. Monitorear Recuperación
- Verificar cada 30 min si endpoint vuelve
- Una vez OK → ejecutar sync manual
- Validar gap de datos

## Mensaje al Cliente (BORRADOR - NO ENVIAR)

```
Asunto: Actualización - Sistema de Pagos Parrotfy Temporalmente No Disponible

Estimado cliente,

Le informamos que estamos experimentando una interrupción temporal en la sincronización automática de datos de pagos desde Parrotfy debido a un problema técnico en su API externa.

Estado actual:
- ✅ Facturas: Sincronizadas correctamente
- ✅ Inventario: Sincronizado correctamente
- ⏸️ Pagos: Temporalmente suspendidos (problema externo)

Acciones tomadas:
1. Identificado el problema (error 500 en endpoint de pagos Parrotfy)
2. Escalado a soporte técnico de Parrotfy
3. Monitoreo continuo para detectar recuperación

Impacto:
- Los reportes de pagos pueden no reflejar las últimas transacciones
- Una vez resuelto, sincronizaremos automáticamente el gap de datos

Próximos pasos:
Le mantendremos informado del progreso. Estimamos resolución en [PLAZO SEGÚN RESPUESTA PARROTFY].

Saludos,
Equipo Monstruo
```

**⚠️ NO ENVIAR ESTE MENSAJE SIN APROBACIÓN MANUAL**

## Resolución Típica

**Tiempo promedio**: 2-8 horas (depende de Parrotfy)

**Próximos pasos una vez resuelto**:
1. Ejecutar sync manual: `python3 sync_parrotfy_payments.py --force`
2. Verificar gap: comparar último payment_id antes/después
3. Cerrar ticket workflow
4. Informar a cliente (si corresponde)

## Contacto Soporte Parrotfy

- **Email**: soporte@parrotfy.com
- **Request IDs**: Incluir en email (ver evidencia)
- **Prioridad**: Alta (afecta múltiples clientes)

---

**Última actualización**: 2026-01-24  
**Autor**: Sistema Monstruo  
**Versión**: 1.0
