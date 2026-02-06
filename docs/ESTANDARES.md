# ESTÁNDARES Y POLÍTICAS - PROYECTO MONSTRUO

Este documento consolida todas las normas, estándares y políticas del proyecto.

---

## 1. ESTÁNDAR DE AGENTES IA & ORQUESTACIÓN

### Roles Definidos

#### A. El Orquestador (ChatGPT / DeepSeek / Claude)
- **Función:** "Arquitecto y Jefe de Proyecto"
- **Responsabilidad:** 
  - Mantiene el "Big Picture" del proyecto
  - Genera planes paso a paso
  - Toma decisiones de diseño de alto nivel
- **Input:** Consultas del usuario, reportes de estado
- **Output:** Instrucciones claras, bloques de código conceptuales, planes de implementación

#### B. El Agente Especialista (Antigravity / IDE Agent)
- **Función:** "Ingeniero Senior & DevOps"
- **Responsabilidad:**
  - Ejecuta comandos en la terminal (`/bin/bash`)
  - Edita archivos reales en el sistema de archivos (`/srv/...`)
  - Verifica que el código funcione (Tests, Logs)
  - Mantiene la "Bitácora de Vuelo" (`PROYECTO_CONTEXTO.md`)
- **Input:** Prompt Universal + Instrucciones del usuario
- **Output:** Software funcionando, Logs de ejecución, Archivos actualizados

### Flujo de Trabajo: Context Switching (Rotación de Contexto)

Los contextos de LLM se degradan con el tiempo. Para mitigar esto, usamos **Relevo de Contexto**.

**¿Cuándo Rotar?**
1. **Latencia Alta:** Cuando el chat tarda mucho en responder
2. **Confusión:** Cuando el agente alucina rutas o archivos viejos
3. **Cambio de Fase:** Al terminar un módulo grande

**¿Cómo Rotar?**
1. En el Chat Viejo: Actualizar `docs/PROYECTO_CONTEXTO.md` y ejecutar `python3 ops/herramientas/generate_universal_prompt.py`
2. En el Chat Nuevo: Pegar contenido de `docs/PROMPT_CHAT_UNIVERSAL.md`

### Reglas de Seguridad & Operación
- **Sudo sin Interrupciones:** Configurar `SUDO_PASS` en `.env` local
- **Verdad Única:** Si no está en `docs/PROYECTO_CONTEXTO.md`, no existe
- **Sin Archivos Basura:** No crear `v1`, `bkp`, `final`. Usar Git o sobreescribir

---

## 2. ESTÁNDAR UI - INTERFAZ EN ESPAÑOL

### Principio Fundamental
**Toda la interfaz visible para el usuario debe estar estrictamente en español.**

### Reglas de Implementación
- **NO renombrar rutas ni archivos:** `dashboard.html` sigue llamándose así internamente
- **Solo textos visibles:** Cambiar `<title>Dashboard</title>` por `<title>Panel Principal</title>`
- **Variables de código:** Mantener `status = 'pending'`, pero mostrar "Pendiente" en la UI

### Glosario Canónico

#### Términos Generales
| Español (UI) | English (interno) | Notas |
|--------------|-------------------|-------|
| **Asistente** | Assistant | Nunca "Ayudante" o "Guía" |
| **Recomendaciones** | Recommendations | - |
| **Aprobaciones** | Approvals | - |
| **Casos** | Cases / Tickets | - |
| **Tareas** | Tasks | - |
| **Comentarios** | Comments | - |
| **Alertas** | Alerts | - |
| **Discrepancias** | Discrepancies | - |
| **Integraciones** | Integrations | - |
| **Cumplimiento** | Compliance | - |
| **Panel Principal** | Dashboard / Home | - |
| **Flujo de Trabajo** | Workflow | - |

#### Estados Canónicos
| Español | English | Código interno |
|---------|---------|----------------|
| **Abierto** | Open | `open` |
| **En Proceso** | In Progress | `in_progress`, `doing` |
| **Listo** | Done | `done` |
| **Bloqueado** | Blocked | `blocked` |
| **Pendiente** | Pending | `pending` |
| **Aprobado** | Approved | `approved` |
| **Rechazado** | Rejected | `rejected` |
| **Error** | Error / Failed | `error`, `failed` |
| **Conectado** | Connected | `connected` |
| **Desconectado** | Disconnected | `disconnected` |

#### Botones y Acciones
| Español | English |
|---------|---------|
| **Guardar** | Save |
| **Cancelar** | Cancel |
| **Eliminar** | Delete |
| **Editar** | Edit |
| **Ver Detalle** | View Detail |
| **Aprobar** | Approve |
| **Rechazar** | Reject |
| **Sincronizar Ahora** | Sync Now |
| **Actualizar** | Update / Refresh |
| **Cerrar** | Close |

#### Secciones Comunes
| Español | English |
|---------|---------|
| **Resumen** | Summary / Overview |
| **Detalles** | Details |
| **Historial** | History |
| **Configuración** | Settings |
| **Perfil** | Profile |
| **Ayuda** | Help |
| **Cerrar Sesión** | Logout |

### Excepciones
- **Nombres técnicos:** API, JSON, URL, HTTP, SQL → se mantienen
- **Nombres propios:** Zabbix, Ollama, Parrotfy, Laudus → se mantienen
- **Variables de código:** mantener en inglés (`created_at`, `task_id`)

### Reglas de Consistencia
1. **NO inventar:** Si no está en este glosario, consultar antes de crear nuevo término
2. **Una sola traducción:** No mezclar "Asistente"/"Ayudante"/"Guía"
3. **Keys JSON:** mantener en inglés para APIs, traducir solo en frontend

---

## 3. POLÍTICAS DE PROYECTO

### Estructura de Proyecto Estándar
Cualquier nuevo proyecto debe tener al menos:
- `/srv/[proyecto]/docs/PROYECTO_CONTEXTO.md` (Bitácora)
- `/srv/[proyecto]/ops/herramientas/generate_universal_prompt.py` (Script Relevo)

### Actualización de Estándares
Cuando se necesite agregar nuevo término o política:
1. Proponer en issue/comentario
2. Validar que no exista similar
3. Agregar aquí con consenso
4. Actualizar código afectado

---

**Última actualización:** 2026-01-27
