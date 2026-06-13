# Ticketera V3 (Módulo de Mesa de Ayuda)

Este microservicio es el núcleo de la gestión de casos internos de MONSTRUO. Reemplaza el uso de mesas externas mediante una operación interna de estándar profesional.

## Objetivo
Unificar la gestión de casos internos (operación, incidentes, proyectos, preventa, integraciones) y automatizar el flujo de trabajo, las notificaciones y los acuerdos de nivel de servicio (SLAs).

## Arquitectura y Módulos Principales
La aplicación está estructurada bajo el patrón **Package-by-Feature** separando claramente el backend del frontend:

*   `backend/`: Contiene la aplicación FastAPI, rutas (`api/`), lógica de negocio (`services/`), y tareas asíncronas (`jobs/`).
*   `ui/`: Contiene la interfaz de usuario en Vanilla JS, HTML y CSS.

## Tipos de Ticket
*   **Operación interna** (finanzas, bodega, crm)
*   **Incidente** (monitoring, alertas de Zabbix)
*   **Proyecto** (entregables)
*   **Preventa** (cotización/configuración)
*   **Integración** (errores de APIs externas)

## Ciclo de Vida y Estados
Los tickets fluyen a través de una secuencia principal estricta:
`NUEVO (Abierto) -> TRIAGE -> EN_PROGRESO -> RESUELTO -> CERRADO`

También soporta flujos complejos y subestados: `pendiente_aprobacion`, `en_ejecucion`, etc.

## SLAs (Service Level Agreements)
El motor de SLA soporta modalidades 24x7 o en Horario Hábil (Business Hours configurables).
Los objetivos operativos actuales (ajustables vía `.env` o base de datos) son:
*   **FRT (First Response Time - Auto-respuesta):** Objetivo <= 30 minutos.
*   **FRT (Tiempo de Asignación):** Objetivo <= 1 hora.
*   **TTR (Time to Resolution):** Objetivo <= 2.5 horas.

## Características Clave (Features)
1.  **Ingesta de Correos (Email Polling):** Permite crear tickets o responder a hilos existentes directamente enviando un correo a la casilla de soporte. Maneja imágenes `inline` y bloquea remitentes no deseados (`blocklist`).
2.  **Respuestas desde la UI:** El especialista puede responder correos directamente desde el detalle del ticket, manteniendo el hilo (thread match) y adjuntando evidencia.
3.  **Auto-Asignación:** Round-robin inteligente basado en la carga actual de los técnicos y su especialidad (`redes`, `sistemas`, `ejecucion`, etc.).
4.  **Notificaciones Escalonadas:**
    *   Inmediata: In-App (campanita).
    *   +5 min: WhatsApp / Telegram.
    *   +20 min: Llamada telefónica (3CX).
5.  **Papelera Blanda:** Los tickets basura generados por correos spam pueden enviarse a la papelera sin alterar los KPIs, pudiendo ser restaurados en caso de error.

## Seguridad y Compliance (ISO 27001)
El módulo genera evidencia con huellas criptográficas (hash chain) para acciones críticas: creación, borrado, respuesta a clientes y aplicación de "Legal Holds" sobre datos.