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

- `plataforma/docs/PROYECTO_CONTEXTO.md` (bitácora y estado actual)
- `AGENTS.md` en la raíz (reglas operativas multi-agente — convención Codex/Cursor/Aider/Gemini)
- `CLAUDE.md` en la raíz (puntero específico para Claude Code)
- `.claude/` en la raíz (configuración específica de Claude Code: subagentes, hooks)

### Actualización de Estándares
Cuando se necesite agregar nuevo término o política:
1. Proponer en issue/comentario
2. Validar que no exista similar
3. Agregar aquí con consenso
4. Actualizar código afectado

---

**Última actualización:** 2026-01-27
