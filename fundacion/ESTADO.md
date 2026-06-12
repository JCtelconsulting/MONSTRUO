# Estado — Fundación (Acompañando Pasos)

**Actualizado:** 2026-06-12

## ⚠️ Situación especial (leer antes de tocar)
El desarrollo grande de Fundación (planificación con calendario Día/Semana/Mes,
catálogo de actividades, plan oficial por nivel, reportería pedagógica, sync
Google Sheets→DB, roles del organigrama 2026, scope por sede) vive en la rama
**`archivo/dev-pre-regularizacion-20260612`**, NO en `dev`. La rama `dev`
actual tiene la versión vieja del módulo.

Además, el contenedor `monstruo-dev-fundacion` fue reconstruido el 2026-06-12
desde el árbol viejo (durante la migración de Terreneitor) → **está corriendo
la versión vieja**. Si alguien de Fundación reporta "desaparecieron funciones",
esta es la causa.

## Tarea #1
Fusionar la línea archivada a `dev` (ver PROYECTO_CONTEXTO decisión #1) y
reconstruir el contenedor. Con eso Fundación recupera todo lo nuevo.

## Pendiente menor (de la línea archivada)
- Configurar `GOOGLE_CHAT_*` en PROD (memoria del proyecto: validación runtime
  ya cerrada 2026-05-05).
