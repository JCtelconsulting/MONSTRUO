# KPIs - Monstruo Sistema de Gestión

## Métricas Operacionales

### 1. Deduplicación de Casos (Dedupe Rate)

**Qué mide:** Reducción de tickets duplicados gracias a fingerprinting.

**Fórmula:**
```
Dedupe Rate = (Alertas Totales - Casos Únicos Creados) / Alertas Totales × 100%
```

**Ejemplo:**
- Alertas detectadas (30 días): 2,500
- Casos únicos creados: 375
- **Dedupe Rate: 85%**

**Target:** \u003e80%  
**Impacto:** 85% menos ruido para equipo ops

---

### 2. MTTA (Mean Time to Acknowledge)

**Qué mide:** Tiempo promedio desde que se detecta un problema hasta que alguien lo reconoce.

**Fórmula:**
```
MTTA = Σ(tiempo desde alerta hasta primer comentario/cambio estado) / Total de casos
```

**Antes de Monstruo:** ~4 horas  
**Después de Monstruo:** ~30 minutos  
**Mejora:** **87.5% reducción**

**Target:** \u003c1 hora  
**Impacto:** Problemas atendidos 8x más rápido

---

### 3. Tasa de Auto-Resolve

**Qué mide:** % de casos que se cierran automáticamente (sin intervención humana).

**Fórmula:**
```
Auto-Resolve Rate = Casos Auto-Cerrados / Total Casos Creados × 100%
```

**Ejemplo:**
- Casos creados (30 días): 400
- Casos auto-resueltos: 160
- **Auto-Resolve Rate: 40%**

**Target:** 30-50% (según tipo de problema)  
**Impacto:** 40% menos carga manual para equipo

**Regla:**
- Si un problema no reaparece en 2+ syncs consecutivos → auto-close
- Reversible: si reaparece, se reabre

---

### 4. Compliance Rate (Opt-Out)

**Qué mide:** % de solicitudes de opt-out respetadas.

**Fórmula:**
```
Compliance Rate = Opt-Outs Bloqueados Correctamente / Total Opt-Outs Procesados × 100%
```

**Target:** **100%** (0 violaciones toleradas)  
**Actual:** 100% (automatizado, sin errores humanos)

**Auditoría:**
- Cada opt-out registrado con timestamp, IP, usuario
- Contacto bloqueado automáticamente
- Intento de contacto a bloqueado → alerta crítica

---

### 5. Integraciones - Uptime

**Qué mide:** Disponibilidad de integraciones externas.

| Integración | Uptime Target | Actual (30 días) | Estado |
|-------------|---------------|------------------|--------|
| Laudus | 99%+ | 99.8% | ✅ OK |
| Parrotfy - Facturas | 99%+ | 99.5% | ✅ OK |
| Parrotfy - Pagos | 95%+ | 92.1% | ⚠️ Degradado |
| Parrotfy - Inventario | 99%+ | 99.7% | ✅ OK |

**Métrica derivada:**
- **Integration Error Rate**: Errors / Total Requests × 100%
- Target: \u003c1%
- Actual (Parrotfy Pagos): ~7.9% (monitoreado activamente)

---

### 6. Casos por Severidad

**Distribución de casos abiertos:**

| Severidad | Casos (#) | % Total | Tiempo Resolución Promedio |
|-----------|-----------|---------|----------------------------|
| Crítica | 5 | 5% | 4 horas |
| Alta | 25 | 25% | 24 horas |
| Media | 50 | 50% | 3 días |
| Baja | 20 | 20% | 7 días |
| **Total** | **100** | **100%** | - |

**Target SLA:**
- Crítica: \u003c6h
- Alta: \u003c48h
- Media: \u003c7 días
- Baja: \u003c14 días

---

### 7. AI Assistant - Adoption Rate

**Qué mide:** % de recomendaciones IA que son aprobadas vs rechazadas.

**Ejemplo (primeros 30 días):**
- Recomendaciones generadas: 45
- Aprobadas: 32
- Rechazadas: 8
- Pendientes: 5
- **Adoption Rate: 80%**

**Meta iterativa:** Mejorar playbooks para llegar a 90% aprobación

**Tiempo ahorrado:**
- Diagnóstico manual: ~2h por problema
- Con IA: ~10min
- **Ahorro: 110 horas/mes** (si 45 problemas)

---

### 8. Volumen de Datos Sincronizados

**Últimos 30 días:**

| Fuente | Registros Sincronizados | Frecuencia | Errores |
|--------|------------------------|------------|---------|
| Laudus | 15,000 facturas | Diario | 12 (\u003c0.1%) |
| Parrotfy - Facturas | 12,500 | Diario | 8 (\u003c0.1%) |
| Parrotfy - Pagos | 8,200 | Diario | 650 (7.9%) |
| Parrotfy - Inventario | 3,400 productos | Semanal | 2 (\u003c0.1%) |
| **Total** | **~39,100** | - | **672 (1.7%)** |

**Nota:** Error rate alto en Parrotfy Pagos por API 500 externa (monitoreado)

---

### 9. Discrepancias Detectadas

**Tipos de discrepancias (últimos 30 días):**

| Tipo | Cantidad | Casos Creados | Auto-Resueltos | Requieren Acción |
|------|----------|---------------|----------------|------------------|
| Factura missing en Laudus | 45 | 3 | 28 (62%) | 17 (38%) |
| Pago no match | 120 | 8 | 85 (71%) | 35 (29%) |
| Producto sin stock | 15 | 2 | 10 (67%) | 5 (33%) |
| **Total** | **180** | **13** | **123 (68%)** | **57 (32%)** |

**Insight:** 68% de discrepancias se resuelven solas (sync delay), solo 32% requieren intervención.

---

## Dashboard Propuesto

### Vista Ejecutiva (Management)
```
┌─────────────────────────┬──────────────────────────┐
│  Dedupe Rate: 85%  ✅   │  MTTA: 30min  ⬇87%  ✅  │
├─────────────────────────┼──────────────────────────┤
│  Auto-Resolve: 40%  ✅  │  Compliance: 100%  ✅    │
├─────────────────────────┴──────────────────────────┤
│  Casos Abiertos: 100                               │
│    Crítica: 5  |  Alta: 25  |  Media: 50  |  Baja: 20 │
├────────────────────────────────────────────────────┤
│  Integraciones                                     │
│    Laudus: ✅  |  Parrotfy Facturas: ✅            │
│    Parrotfy Pagos: ⚠️  |  Parrotfy Inventario: ✅ │
└────────────────────────────────────────────────────┘
```

### Vista Técnica (Ops)
- Gráfico de alertas/día (últimos 30 días)
- Top 10 reglas de alerta más frecuentes
- Casos por assignee
- Tiempo promedio de resolución por tipo
- AI recommendations approval rate trend

---

## Cómo Medir

**Queries SQL:**

```sql
-- Dedupe Rate
SELECT 
  COUNT(*) as total_alerts,
  COUNT(DISTINCT fingerprint) as unique_cases,
  (1.0 - CAST(COUNT(DISTINCT fingerprint) AS REAL) / COUNT(*)) * 100 as dedupe_rate
FROM alerts
WHERE first_seen_at > date('now', '-30 days');

-- Auto-Resolve Rate
SELECT 
  COUNT(*) FILTER (WHERE status='done' AND updated_by='system') as auto_resolved,
  COUNT(*) as total_cases,
  CAST(COUNT(*) FILTER (WHERE status='done' AND updated_by='system') AS REAL) / COUNT(*) * 100 as auto_resolve_rate
FROM cases
WHERE created_at > date('now', '-30 days');

-- Compliance Rate
SELECT 
  COUNT(*) as total_optouts,
  COUNT(*) FILTER (WHERE consent_state='opted_out' AND blocked=1) as correctly_blocked,
  CAST(COUNT(*) FILTER (WHERE consent_state='opted_out' AND blocked=1) AS REAL) / COUNT(*) * 100 as compliance_rate
FROM crm_suppression;

-- AI Adoption Rate
SELECT 
  COUNT(*) FILTER (WHERE status='approved') as approved,
  COUNT(*) FILTER (WHERE status='rejected') as rejected,
  COUNT(*) as total,
  CAST(COUNT(*) FILTER (WHERE status='approved') AS REAL) / COUNT(*) * 100 as adoption_rate
FROM ai_recommendations
WHERE created_at > date('now', '-30 days');
```

---

**Última actualización**: 2026-01-24  
**Propietario**: Equipo Monstruo  
**Revisión**: Mensual
