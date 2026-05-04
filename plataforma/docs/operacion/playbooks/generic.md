# Playbook: Problema Genérico - Template

## Contexto

Este playbook se usa cuando **no hay un playbook específico** para el tipo de evento o alerta detectada.

## Uso

El Asistente IA debe analizar el evento y proporcionar:
1. Resumen del problema
2. Diagnóstico inicial basado en datos disponibles
3. Acciones recomendadas generales

## Template de Análisis

### 1. Identificar Tipo de Problema

**Categorías comunes:**
- 🔌 Integración externa (API error)
- 💾 Base de datos (query failed, constraint violation)
- 📊 Discrepancia de datos (mismatch entre sistemas)
- ⚠️ Alerta de negocio (threshold exceeded)
- 🔒 Seguridad/Compliance (unauthorized access, opt-out)
- 🔄 Workflow (task stuck, case blocked)

### 2. Extraer Información Clave

```python
{
    "source": "<SISTEMA_ORIGEN>",
    "kind": "<TIPO_EVENTO>",
    "severity": "<low|medium|high|critical>",
    "affected_entity": "<ENTIDAD_AFECTADA>",
    "error_message": "<MENSAJE_ERROR>",
    "first_seen": "<TIMESTAMP>",
    "occurrences": <COUNT>
}
```

### 3. Diagnóstico Inicial

**Preguntas a responder:**
- ¿Es un problema nuevo o recurrente?
- ¿Afecta a un solo registro o múltiples?
- ¿Hay patrón temporal? (horario, día de semana)
- ¿Sistemas relacionados están OK?

### 4. Severidad Estimada

```python
if occurrences > 100:
    severity = "high"  # Problema masivo
elif occurrences > 10:
    severity = "medium"  # Problema recurrente
else:
    severity = "low"  # Incidente aislado

if "critical" in kind or "error" in kind:
    severity = max(severity, "medium")
```

## Acciones Recomendadas Genéricas

### Para Errores de Integración
1. Verificar conectividad: `curl <ENDPOINT>`
2. Revisar logs: `tail -100 /srv/monstruo_dev/data/logs/<service>.log`
3. Verificar credenciales: revisar `.env`
4. Probar endpoint manualmente

### Para Discrepancias de Datos
1. Query de verificación en ambos sistemas
2. Comparar timestamps de última actualización
3. Ejecutar sync manual si corresponde
4. Validar lógica de normalización

### Para Alertas de Negocio
1. Verificar threshold configurado
2. Analizar tendencia histórica
3. Confirmar con stakeholder si es anómalo
4. Ajustar threshold si falso positivo

### Para Problemas de Workflow
1. Ver caso/tarea bloqueada
2. Identificar dependencias
3. Verificar assignee disponible
4. Escalar si bloqueado \u003e48h

## Creación de Tarea

**Template genérico:**
```
Título: <KIND> - <BRIEF_DESCRIPTION>
Prioridad: <SEVERITY>
Asignado a: <ROLE_BASED_ON_KIND>
Descripción:
  Fuente: <SOURCE>
  Tipo: <KIND>
  Severidad: <SEVERITY>
  Entidad afectada: <ENTITY>
  Primera detección: <FIRST_SEEN>
  Occurrencias: <COUNT>
  
  Error: <ERROR_MESSAGE>
  
  Acciones sugeridas:
  1. <ACTION_1>
  2. <ACTION_2>
  3. <ACTION_3>
  
  Logs: /srv/monstruo_dev/data/logs/<service>.log
```

## Mapeo Rol por Tipo

```python
ROLE_MAP = {
    "integration": "ops",
    "database": "ops",
    "discrepancy": "finance",
    "compliance": "admin",
    "workflow": "ops",
    "security": "admin",
}

assigned_to = ROLE_MAP.get(category, "ops")  # default ops
```

## Mensaje al Cliente (BORRADOR - NO ENVIAR)

```
Asunto: Notificación Técnica - <BRIEF_DESCRIPTION>

Estimado cliente,

Hemos detectado <DESCRIPTION> en nuestro sistema de monitoreo.

Detalles:
- Tipo: <KIND>
- Severidad: <SEVERITY_ESPAÑOL>
- Estado: En investigación

Acciones tomadas:
1. Problema identificado y registrado
2. Equipo técnico notificado
3. Monitoreo activo

Próximos pasos:
Le mantendremos informado del progreso. Tiempo estimado de resolución: <ESTIMATE>.

Saludos,
Equipo Monstruo
```

**⚠️ NO ENVIAR ESTE MENSAJE SIN APROBACIÓN MANUAL**

## Escalación

**Escalar a humano si:**
- Severity = "critical"
- Occurrences \u003e 100 en \u003c1 hora
- Involucra datos de cliente sensibles
- No hay contexto suficiente para diagnosticar
- Problema nuevo sin precedente

## Limitaciones

⚠️ **Este playbook es genérico y puede no capturar detalles específicos**.

**Recomendación**: Crear playbooks específicos para:
- Problemas recurrentes
- Errores con patrón conocido
- Flujos de negocio críticos

---

**Última actualización**: 2026-01-24  
**Autor**: Sistema Monstruo  
**Versión**: 1.0
