# Estado — GTA (Gestión de Tareas Automatizadas)

**Actualizado:** 2026-06-12

## ⚠️ Situación especial (leer antes de tocar)
TODO el código de GTA (editor visual de procesos/diagramas, checklist de items
por paso, tablero, flujos cross-área con SLA, devoluciones, membresías por
área) vive en la rama **`archivo/dev-pre-regularizacion-20260612`**, NO en
`dev` (en dev GTA casi no existe). En el disco de la VM, `gta/` está presente
pero **untracked** (quedó del checkout anterior).

El contenedor `monstruo-dev-gta:9012` corre la versión nueva (lleva ~3 semanas
arriba, NO fue reconstruido) y está **fuera del docker-compose raíz** (legacy).
Mientras no se haga el merge: NO reconstruir ese contenedor (se perdería la
versión nueva en runtime) y NO borrar la carpeta `gta/` del disco.

## Tarea #1
Fusionar la línea archivada a `dev` (ver PROYECTO_CONTEXTO decisión #1), agregar
GTA al compose raíz y reconstruir desde el repo.

## Datos
- Tareas se asignan a ÁREAS (no personas); GTA y "Tareas" son la misma app
  (los procesos detonan tareas) — ver memoria del proyecto.
