# Guión de Demostración Monstruo - 7-10 minutos

## Preparación

**Antes de la demo:**
- ✅ Servicio running: `ps aux | grep uvicorn`
- ✅ DB con data de ejemplo
- ✅ Browser en http://127.0.0.1:8000/ui/hub.html
- ✅ Modo DEMO activado (opcional): `DEMO_MODE=1` en `.env`

---

## Minuto 1-2: Introducción + Contexto

**Mensaje:**
> "Monstruo es nuestro sistema de gestión operativa que centraliza integraciones, detecta discrepancias, y automatiza workflow.  
> Hoy les mostraré 4 módulos clave: Dashboard, Workflow, CRM con Cumplimiento, y nuestro nuevo Asistente IA."

**Acción:**
- Mostrar **hub.html** (Panel Principal)
- Señalar: "Estado de integraciones en tiempo real"
  - Laudus: ✅ Conectado
  - Parrotfy Facturas: ✅ OK
  - Parrotfy Pagos: ⚠️ Degradado (error 500 - caso de uso)
- Señalar: "Última sincronización: hace 2 horas, 150 registros"

---

## Minuto 3-4: Workflow - Gestión de Casos

**Mensaje:**
> "Cuando detectamos discrepancias entre sistemas, creamos casos automáticamente.  
> Ejemplo: 15 facturas de Parrotfy sin match en Laudus."

**Acción:**
1. Click en **"Flujo de Trabajo"**
2. Mostrar lista de casos activos
3. Abrir un caso: **"Parrotfy Missing Invoices - Case #1"**
4. Señalar:
   - **Deduplicación**: "20 alertas → 1 solo caso (sin duplicados)"
   - **Auto-resolve**: "Si la factura aparece en próximas X horas, se cierra automáticamente"
   - **Comentarios**: "Historial de acciones del sistema"
5. Cambiar estado: `Abierto` → `En Proceso` → mostrar badge actualizado

**Key point:**
> "Antes teníamos 50 tickets duplicados por día. Ahora: **1 ticket por problema único**."

---

## Minuto 5-6: CRM + Cumplimiento

**Mensaje:**
> "Integramos CRM con compliance RGPD.  
> Detectamos automáticamente cuando un cliente solicita opt-out y bloqueamos contacto."

**Acción:**
1. Click en **"CRM"**
2. Buscar empresa: "Empresa Demo S.A."
3. Mostrar contactos asociados
4. Señalar tabla **Opt-Out Requests**:
   - Email X solicitó opt-out hace 2 días
   - Estado: **Bloqueado** (no se puede contactar)
5. Señalar: "Auditoría completa: quién, cuándo, por qué"

**Key point:**
> "Cumplimiento automático. Si alguien intenta enviar email a contacto bloqueado, **el sistema lo previene**."

---

## Minuto 7-8: Asistente IA (★ Novedad)

**Mensaje:**
> "Nuevo: Asistente IA que analiza eventos, consulta playbooks internos, y genera recomendaciones."

**Acción:**
1. Click en **"Asistente IA"**
2. Mostrar lista de recomendaciones pendientes:
   - **"Parrotfy Payments API 500 - Sincronización Bloqueada"**
   - Estado: **Pendiente**
3. Abrir detalle:
   - **Resumen**: "Endpoint /api/v1/payments retorna 500. Problema del lado de Parrotfy."
   - **Diagnóstico**: "90% probabilidad servicio caído temporalmente"
   - **Acciones recomendadas**:
     - Verificar endpoint directamente
     - Revisar request IDs en logs
     - Escalar a soporte Parrotfy si persiste \u003e24h
   - **Borrador mensaje cliente**: (mostrar pero **no enviar**)
4. Click en **"Aprobar"**
   - Mostrar: "Recomendación aprobada. Se creará ticket automáticamente."

**Key point:**
> "La IA **no toma decisiones**, solo sugiere. Humano aprueba o rechaza.  
> Esto reduce tiempo de diagnóstico de **2 horas → 10 minutos**."

---

## Minuto 9: Métricas e Impacto

**Mostrar slide o verbal:**

### KPIs Actuales
- **Deduplicación**: 85% menos tickets duplicados
- **Auto-resolve**: 40% de casos se cierran automáticamente
- **MTTA (Mean Time to Acknowledge)**: Reducido de 4h → 30min
- **Compliance**: 100% opt-outs respetados (0 violaciones)
- **Integraciones**: 3 sistemas integrados (Laudus, Parrotfy, futuro: Zabbix)

### Beneficios
✅ **Eficiencia**: Equipo ops se enfoca en problemas reales, no duplicados  
✅ **Trazabilidad**: Cada acción auditada  
✅ **Compliance**: Automático, sin errores humanos  
✅ **Escalabilidad**: Mismo equipo gestiona 3x más volumen de datos  

---

## Minuto 10: Conclusiones + Próximos Pasos

**Mensaje:**
> "**Monstruo centraliza, automatiza y cumple.**  
> No somos dependientes de vendors: arquitectura modular, sin lock-in.  
> Próximo paso: integrar Zabbix para monitoreo de infraestructura."

**Próximas features:**
1. **Dashboard de métricas**: KPIs en tiempo real
2. **App móvil**: Notificaciones push para casos críticos
3. **Zabbix integration**: Alertas de servidores → workflow automático
4. **AI mejorada**: Aprendizaje de resoluciones pasadas

**Preguntas:**
- ¿Qué otras integraciones necesitan?
- ¿Qué métricas les gustaría ver en dashboard?

---

## Tips para la Demo

### Preparar Data de Ejemplo
```bash
# Asegurar que hay casos activos
sqlite3 /srv/monstruo_dev/data/db/monstruo.db "SELECT COUNT(*) FROM cases WHERE status='open';"
# Mínimo 3-5 casos

# Asegurar recomendaciones IA
sqlite3 /srv/monstruo_dev/data/db/monstruo.db "SELECT COUNT(*) FROM ai_recommendations WHERE status='pending';"
# Mínimo 1 recomendación
```

### Durante la Demo
- **Hablar lento y claro**
- **Pausar para preguntas** después de cada módulo
- **No tocar código**: solo UI
- **Si algo falla**: tener backup plan (screenshots)

### Modo DEMO
Si `DEMO_MODE=1`:
- Banner **"DEMO"** visible
- Emails/teléfonos ofuscados (xxx@xxx.com)
- Sin eliminar data real

---

**Duración total**: ~10 minutos  
**Nivel técnico**: Bajo-medio (para management)  
**Objetivo**: Mostrar **valor de negocio**, no arquitectura técnica
