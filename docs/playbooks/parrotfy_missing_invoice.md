# Playbook: Factura de Parrotfy No Encontrada en Laudus

## Contexto

Una o más facturas presentes en Parrotfy **no tienen match en Laudus**, indicando posible gap de sincronización o problema de datos.

## Síntomas

- 📊 Discrepancia detectada: `parrotfy_invoice_missing_in_laudus`
- ❌ Folio X existe en Parrotfy pero no en Laudus
- ⚠️ Puede ser una factura o múltiples

## Diagnóstico Probable

1. **Factura Reciente (50% probabilidad)**
   - Creada en últimas 24-48h
   - Laudus aún no la procesó
   - **Acción**: Esperar siguiente sync

2. **Gap Histórico en Laudus (30%)**
   - Factura antigua (\u003e30 días)
   - Nunca llegó a Laudus por problema pasado
   - **Acción**: Investigar causa raíz

3. **Factura Anulada/Cancelada (15%)**
   - Existe en Parrotfy pero fue anulada
   - Laudus la ignora correctamente
   - **Acción**: Verificar estado en Parrotfy

4. **Problema de Normalización (5%)**
   - Folio mal formateado
   - Mismatch en formato de números
   - **Acción**: Revisar lógica de normalización

## Checklist de Verificación

### Paso 1: Ver Detalles de la Factura

```sql
-- Buscar en Parrotfy
SELECT parrotfy_invoice_id, parrotfy_invoice_number, 
       total, created_at, raw_json
FROM parrotfy_invoices
WHERE parrotfy_invoice_number = '<FOLIO>';

-- Buscar en Laudus (por si está con otro formato)
SELECT * FROM laudus_invoices
WHERE raw_json LIKE '%<FOLIO>%';
```

### Paso 2: Verificar Fecha de Creación

```python
# Si factura tiene < 48 horas
from datetime import datetime, timedelta

factura_date = datetime.fromisoformat(created_at)
now = datetime.now()
age_hours = (now - factura_date).total_seconds() / 3600

if age_hours < 48:
    # Es reciente, probablemente sync pendiente
    action = "WAIT"
else:
    # Es antigua, gap real
    action = "INVESTIGATE"
```

### Paso 3: Revisar Estado en Parrotfy

```bash
# API call para ver detalles completos
curl "https://api.parrotfy.com/api/v1/invoices/<ID>" \
  -H "Authorization: Bearer <TOKEN>"

# Verificar:
# - status: "active" / "cancelled" / "voided"
# - type: "invoice" / "credit_note"
```

### Paso 4: Verificar Última Sincronización Laudus

```sql
SELECT source, started_at, finished_at, status, records_inserted
FROM import_runs
WHERE source = 'laudus'
ORDER BY started_at DESC LIMIT 5;
```

**Si última sync fue hace \u003e24h → sync manual recomendado**

## Riesgos e Impacto

### Alto Riesgo
- **Gap acumulado**: Si son muchas facturas, indica problema sistémico
- **Conciliación incorrecta**: Reportes financieros desbal anceados

### Medio Riesgo
- **Factura individual**: Una factura missing es bajo impacto
- **Cliente espera data**: Si cliente consulta, debe estar disponible

### Bajo Riesgo
- **Factura anulada**: No debería estar en Laudus de todas formas

## Acción Interna Sugerida (Solo Workflow)

### 1. Auto-categorizar según Edad

```python
if age_hours < 48:
    # Factura reciente
    priority = "low"
    action = "Monitor próximo sync (24h)"
    
elif age_hours < 168:  # < 7 días
    # Factura semanal
    priority = "medium"
    action = "Sync manual Laudus + verificar"
    
else:  # > 7 días
    # Factura antigua, gap real
    priority = "high"
    action = "Investigar causa raíz + sync manual"
```

### 2. Crear Tarea en Workflow

- **Título**: `Factura Parrotfy <FOLIO> no encontrada en Laudus`
- **Prioridad**: Según edad (low/medium/high)
- **Asignado a**: Finance
- **Descripción**:
  ```
  Folio: <NUMERO>
  Parrotfy ID: <ID>
  Total: $<MONTO>
  Fecha creación: <FECHA>
  Edad: <HORAS>h
  
  Acción recomendada: <ACTION>
  ```

### 3. Si son Múltiples Facturas (\u003e10)

```python
if missing_count > 10:
    # Problema sistémico, escalar
    create_case(
        title=f"{missing_count} facturas Parrotfy missing en Laudus",
        priority="critical",
        description="Gap masivo detectado, requiere investigación urgente"
    )
```

## Mensaje al Cliente (BORRADOR - NO ENVIAR)

```
Asunto: Factura <FOLIO> - Verificación en Proceso

Estimado cliente,

Hemos detectado que la factura <FOLIO> de Parrotfy aún no aparece sincronizada en nuestro sistema Laudus.

Detalles:
- Folio: <NUMERO>
- Monto: $<TOTAL>
- Fecha: <FECHA>
- Estado: En verificación

Acciones en curso:
1. Verificamos que la factura existe correctamente en Parrotfy ✅
2. Ejecutaremos sincronización manual con Laudus
3. Validaremos la aparición en próximas 24 horas

Próximos pasos:
Le confirmaremos una vez la factura esté completamente sincronizada.

Saludos,
Equipo Monstruo
```

**⚠️ NO ENVIAR ESTE MENSAJE SIN APROBACIÓN MANUAL**

## Resolución

### Si Factura es Reciente (\u003c48h)
1. ✅ Marcar task como "Monitoring"
2. ⏱️ Esperar siguiente sync automático
3. 🔍 Verificar en 24h

### Si Factura es Antigua (\u003e7 días)
1. 🔧 Ejecutar sync manual Laudus: `python3 sync_laudus.py --force`
2. 🔍 Verificar si aparece ahora
3. ❌ Si no aparece → Investigar logs históricos
4. 📧 Si necesario, contactar soporte Laudus

### Si son Múltiples Facturas
1. 🚨 Escalar a caso crítico
2. 📊 Analizar patrón (fechas, monto, cliente)
3. 🔧 Sync masivo + validación full

---

**Última actualización**: 2026-01-24  
**Autor**: Sistema Monstruo  
**Versión**: 1.0
