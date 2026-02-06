---
trigger: always_on
---

# gemini.md instrucciones para /srv/monstruo

# REGLAS GLOBALES - VERSION CLARA Y ESTRICTA (v2)

0) META-REGLA DE CUMPLIMIENTO ACTIVO (SIEMPRE)
En cada respuesta debo revisar estas reglas.
Si detecto una violacion, debo detenerme y decir exactamente:
"Ojo, se salto la regla [X]. Como lo corrijo?"
y proponer la correccion inmediata.

0.1) ORDEN DE AUTORIDAD (ANTI-CONFLICTO)
Cuando haya dudas o conflicto, obedecer en este orden:
1) docs/PLAN_MAESTRO_MONSTRUO.md (arquitectura, modulos, EPICs, gates, DoD).
2) docs/PROYECTO_CONTEXTO.md (estado real, bitacora, hitos, decisiones ya tomadas).
3) gemini.md (este archivo: protocolo operativo).
4) Instruccion puntual del usuario (si NO contradice 1-3).

0.2) ANTI-SCOPE-CREEP (CLAVE PARA NO "HACER 10 COSAS")
- 1 tarea por ciclo. Si el usuario pide varias, debo elegir UNA y pedir cual va primero.
- Limites duros por tarea:
  - Max 3 archivos tocados (creado/modificado) por tarea.
  - Max 300 lineas modificadas por archivo.
- Si necesito exceder limites: detener y pedir OK explicito antes de continuar.

1) IDIOMA Y NOMENCLATURA (VITAL)
1.1 Todo en espanol: planes, nombres, tareas, titulos, bitacoras, mensajes.
1.2 Excepcion: keywords del lenguaje (Python/JS) y comandos del sistema (git, systemctl, curl).
1.3 Comentarios/logs/prints: preferible en espanol y sin tildes/ni "ñ" si aplica el estandar del repo.
1.4 Prohibido crear archivos/scripts nuevos con nombre en ingles.
1.5 Si existe algun archivo/carpeta creada por el asistente en ingles, proponer renombre a espanol
    SOLO si no rompe rutas. Si rompe, pedir OK.

2) FLUJO DE TRABAJO PASO A PASO (OBLIGATORIO)
Cada respuesta sigue un ciclo fijo y declarado.

2.1) MODO PLAN (SIN COMANDOS)
Se usa cuando:
- Hay que decidir enfoque, o
- Se tocara codigo/DB/configuracion, y el usuario aun NO dijo "Proceder/Aprobado".
Formato:
- Objetivo del paso
- Referencia (EPIC/Seccion del Plan Maestro)
- Plan (max 5 bullets)
- Archivos a tocar (max 3) o "SIN CAMBIOS"
- Riesgos (1-3 bullets)
- Pregunta de OK (una sola frase)
Cierre obligatorio:
ESTADO: ESPERANDO_OK

2.2) MODO EJECUCION (CON COMANDOS)
Se usa solo cuando el usuario ya dijo "Proceder/Aprobado" o la tarea es 100% segura y de lectura.
Formato:
- Objetivo del paso
- Un solo bloque de comandos (corto)
  - Incluye la verificacion dentro del mismo bloque, al final
- Resultado/Verificacion (PASS/FAIL)
- Bitacora breve (que cambio + como verificar)
Cierre obligatorio:
ESTADO: CERRADO o ESTADO: BLOQUEADO

2.3) PROHIBIDO PROPONER EXTRAS
Hasta cerrar el objetivo del paso, esta prohibido proponer mejoras colaterales, refactors o "ya que estamos".

3) SEGURIDAD Y SECRETOS (CERO CLAVES)
3.1 Prohibido pedir o imprimir secretos.
3.2 Usar .env o variables de entorno.
3.3 Si se requiere sudo: usar SUDO_PASS desde entorno (no pedir interactivo).

4) GESTION DE ARCHIVOS (BACKUPS LIMPIOS Y AUTOMATICOS)
4A) Prohibicion absoluta de backups sueltos
Prohibido crear: *.bak, *.old, *_backup*, copias con sufijos, duplicados manuales o "archivo_final"
dentro de carpetas funcionales.

4B) Backups solo en carpeta dedicada
Si se necesita backup, SOLO se permite bajo:
backups/YYYY-MM-DD/

4C) Formato de backup
HHMMSS__<ruta_relativa_saneada>.<ext>

4D) Retencion maxima obligatoria
Mantener maximo 5 backups por archivo/item.
Al crear el 6to, borrar automaticamente los mas antiguos dentro de backups/.

4E) Limpieza reactiva
Si se detecta un .bak/.old o copia suelta fuera de backups/, aplicar meta-regla y proponer:
- moverlo a backups/YYYY-MM-DD/
- aplicar retencion (max 5)

5) CONTEXTO UNIFICADO (FUENTE DE VERDAD OPERATIVA)
La guia estructural es: docs/PLAN_MAESTRO_MONSTRUO.md
La bitacora y estado real es: docs/PROYECTO_CONTEXTO.md

5A) Inicio de trabajo = nuevo HITO
Al comenzar una conversacion/trabajo nuevo, se crea en docs/PROYECTO_CONTEXTO.md:
HITO: YYYY-MM-DD HH:MM - <titulo corto>
Dentro del hito registrar SIEMPRE:
- Solicitud del usuario
- Entregable del asistente
- Estado (pendiente / en curso / cerrado)

5B) Registro minimo por cada paso ejecutado
Por cada paso (solo en MODO EJECUCION) agregar:
- Objetivo
- Archivos tocados (ruta exacta + creado/modificado)
- Resumen (1 a 5 lineas)
- Verificacion (comando o criterio)
- Rollback (si aplica)

6) ESTANDARES TECNICOS
Backend: Python 3.12 + venv + FastAPI + Uvicorn + SQLAlchemy + SQLite (lab).
Frontend: HTML/JS nativo (sin frameworks pesados innecesarios).
Servicios locales: bind a 127.0.0.1.
Portabilidad: mismo codigo en local y prod, config por env vars.

7) IA LOCAL Y ENTRENAMIENTO (PRACTICO Y MEDIBLE)
7.1 Usar scripts (Python/SQL) para tareas masivas/rapidas.
7.2 Usar LLM local para decisiones ambiguas/cognitivas.
7.3 Regla de modelos: 1 modelo principal + 1 especialista solo si hay mejora medida.
7.4 Toda correccion humana (match manual, duplicado resuelto, etc.) debe quedar registrada para aprendizaje futuro.

8) ARQUITECTURA MULTI-AGENTE (CON LIMITES Y ALARMA)
8A) Contrato obligatorio por agente
Cada agente define:
- Alcance
- Prohibiciones
- Entradas validas
- Salidas esperadas
- Acciones de riesgo (requieren OK)

8B) Alarma por cruce
Si un agente actua fuera de su contrato:
Aplicar meta-regla y decir:
"Ojo, se salto la regla [8A] (cruce de agente). Como lo corrijo?"
y proponer reasignar al agente correcto o pedir OK.

9) SELF-IC (AUTO-MEJORA RESTRINGIDA)
Permitido: UI/UX, correccion de bugs simples, optimizacion de consultas.
Prohibido: acciones destructivas (DROP TABLE, rm -rf, borrar core).
Si hay duda: detener y pedir OK.

10) CIERRE DE HITO Y ROTACION
10.1 Al cerrar un hito, registrar cierre en docs/PROYECTO_CONTEXTO.md.
10.2 Si el chat se satura, sugerir rotacion.

10.3 Regla de nombres en espanol (IMPORTANTE)
Prohibido introducir archivos/scripts nuevos en ingles.
Si ya existe un script con nombre en ingles, es deuda tecnica: proponer renombre con OK o documentar excepcion.

11) RESTRICCIONES TELCONSULTING (OBLIGATORIAS)
11.1 Prohibido introducir referencias a "nextcloud" en codigo, bases de datos, rutas o nombres.
11.2 Prohibido inventar rutas: siempre usar rutas reales del proyecto.
11.3 En laboratorio (1 usuario), NO implementar medidas pensadas solo para multiusuario (cache-bust, locks, rate-limits) salvo que el Plan Maestro lo indique como preparacion.
