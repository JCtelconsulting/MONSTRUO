# Glosario Oficial UI - Español

## Términos Canónicos

| Español (UI) | English (interno) | Notas |
|--------------|-------------------|-------|
| **Asistente** | Assistant | Nunca "Ayudante" o "Guía" |
| **Recomendaciones** | Recommendations | - |
| **Aprobaciones** | Approvals | - |
| **Casos** | Cases | - |
| **Tareas** | Tasks | - |
| **Comentarios** | Comments | - |
| **Alertas** | Alerts | - |
| **Discrepancias** | Discrepancies | - |
| **Integraciones** | Integrations | - |
| **Estado de integraciones** | Integration Status | - |
| **Cumplimiento** | Compliance | - |
| **Consentimiento** | Consent | - |
| **Bloqueo** | Opt-out | - |
| **Panel principal** | Home / Dashboard / Hub | - |
| **Guía de interfaz** | UI Guide | - |

## Estados Canónicos

| Español | English | Código interno |
|---------|---------|----------------|
| **Abierto** | Open | `open` |
| **En proceso** | In Progress / Doing | `doing`, `in_progress` |
| **Listo** | Done | `done` |
| **Bloqueado** | Blocked | `blocked` |
| **Pendiente** | Pending | `pending` |
| **Aprobado** | Approved | `approved` |
| **Rechazado** | Rejected | `rejected` |
| **Error** | Error / Failed | `error`, `failed` |
| **Degradado** | Degraded | `degraded` |
| **Conectado** | Connected | `connected` |
| **Desconectado** | Disconnected | `disconnected` |

## Botones y Acciones

| Español | English |
|---------|---------|
| **Aprobar** | Approve |
| **Rechazar** | Reject |
| **Ver detalle** | View Detail / Details |
| **Crear caso** | Create Case |
| **Sincronizar ahora** | Sync Now |
| **Actualizar** | Update / Refresh |
| **Guardar** | Save |
| **Cancelar** | Cancel |
| **Eliminar** | Delete |
| **Editar** | Edit |
| **Cerrar** | Close |

## Badges / Etiquetas

| Español | Color sugerido | English |
|---------|----------------|---------|
| **PENDIENTE** | Amarillo/Naranja | PENDING |
| **APROBADO** | Verde | APPROVED |
| **RECHAZADO** | Rojo | REJECTED |
| **ERROR** | Rojo | ERROR |
| **DEGRADADO** | Naranja | DEGRADED |
| **CONECTADO** | Verde | CONNECTED |
| **DESCONECTADO** | Gris | DISCONNECTED |

## Secciones Comunes

| Español | English |
|---------|---------|
| **Resumen** | Summary |
| **Detalles** | Details |
| **Historial** | History |
| **Configuración** | Settings / Configuration |
| **Perfil** | Profile |
| **Ayuda** | Help |
| **Cerrar sesión** | Logout / Sign Out |

## Reglas de Uso

1. **Archivos/rutas**: pueden mantener nombres en inglés por compatibilidad (`assistant.html`), pero el contenido visible DEBE ser español.

2. **Keys JSON**: mantener en inglés para APIs (`status`, `kind`, `payload`), traducir solo en frontend.

3. **Estados internos**: mantener códigos en inglés en DB (`open`, `done`), mapear a español en UI.

4. **NO inventar**: Si no está en este glosario, consultar antes de crear nuevo término.

5. **Consistencia**: Una sola traducción por término. No mezclar "Asistente"/"Ayudante"/"Guía".

## Excepciones

- **Nombres técnicos**: API, JSON, URL, HTTP, SQL → se mantienen como están
- **Nombres propios**: Zabbix, Ollama, Parrotfy, Laudus → se mantienen
- **Variables de código**: mantener en inglés (`created_at`, `task_id`)

## Actualización de Glosario

Cuando se necesite agregar nuevo término:
1. Proponer en issue/comentario
2. Validar que no exista similar
3. Agregar aquí con consenso
4. Actualizar UIs afectadas
