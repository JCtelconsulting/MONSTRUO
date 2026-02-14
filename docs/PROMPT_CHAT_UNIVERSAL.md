# PROMPT DE CONTEXTO UNIVERSAL: MONSTRUO (DEV)
**Fecha Generación:** 2026-02-14
**Objetivo:** Bootstrap operativo para iniciar agentes sin perder contexto ni cruzar DEV/PROD.

---

## 1. Mandato de este archivo
Este archivo es solo un **bootstrap**. No reemplaza la documentación canónica.

Orden de autoridad obligatorio:
1. `docs/PLAN_MAESTRO_MONSTRUO.md`
2. `docs/PROYECTO_CONTEXTO.md`
3. `.agent/rules/monstruo-dev-reglas.md`
4. `docs/ESTANDARES.md`
5. Instrucción puntual del usuario (si no contradice 1-4)

---

## 2. Carga obligatoria al iniciar
Antes de proponer o ejecutar cambios, el agente debe cargar:
- `docs/PLAN_MAESTRO_MONSTRUO.md`
- `docs/PROYECTO_CONTEXTO.md`
- `.agent/rules/monstruo-dev-reglas.md`
- `docs/ESTANDARES.md`
- `docs/.README.md`
- `.README.md` de cada carpeta que vaya a tocar (allowlist local)

Frase de control recomendada:
`Contexto cargado: Plan + Contexto + Reglas DEV + Estandares + Allowlists`.

---

## 3. Prioridad de negocio vigente
- **EPIC 11 (Ticketera) = prioridad máxima absoluta.**
- Objetivo: reemplazar mesa externa con estándar profesional.
- No abrir desarrollo neto de EPIC 12+ mientras EPIC 11 no cumpla Go/No-Go del Plan Maestro.

---

## 4. Separación DEV/PROD (no negociable)

| Campo | DEV | PROD |
|---|---|---|
| Rama base | `dev` | `main` |
| Ruta servidor | `/srv/monstruo_dev` | `/srv/monstruo` |
| Env file | `.env.server.dev` | `.env.server` |
| Compose project | `monstruo_dev` | `monstruo` |
| Stack visible | `monstruo-dev` | `monstruo` |
| Puerto API interno | `9001` | `9000` |

Reglas duras:
- Prohibido mezclar `project` (`monstruo-dev` vs `monstruo_dev`).
- Prohibido usar `env` de PROD en tareas DEV.
- Prohibido copiar credenciales/tokens entre entornos.
- Prohibido desplegar a `main` sin autorización explícita del usuario.
- Prohibido editar código en servidor PROD por SSH fuera del flujo CI/CD.

---

## 5. Flujo operativo obligatorio
Cada tarea debe cerrar este ciclo:
1. PLAN breve
2. EJECUCIÓN acotada
3. VERIFICACIÓN con evidencia (PASS/FAIL)
4. CIERRE con cambios + riesgos + siguiente paso

Reglas:
- Una tarea a la vez.
- No meter extras fuera de alcance.
- Si aparece bloqueo, detener y reportar causa real con opción de corrección.

---

## 6. Política de estructura y allowlists
- No crear archivos fuera del árbol oficial definido en `docs/PLAN_MAESTRO_MONSTRUO.md`.
- Respetar allowlists `.README.md` por carpeta.
- Si se requiere crear ruta fuera de allowlist, pedir permiso explícito y registrar el cambio en docs.

---

## 7. Registro documental obligatorio
Si hay cambio de arquitectura/proceso/regla:
- Actualizar `docs/PLAN_MAESTRO_MONSTRUO.md` (política permanente).
- Actualizar `docs/PROYECTO_CONTEXTO.md` (hito operativo con fecha).

---

## 8. Comandos de referencia vigentes
- Regenerar prompt universal:
```bash
python3 ops/herramientas/deploy/generate_universal_prompt.py
```

- Verificar estructura:
```bash
python3 ops/herramientas/deploy/verify_structure.py
```

- Levantar entorno local DEV (ejemplo):
```bash
docker compose --env-file .env up -d
```

---

## 9. Checklist anti-cruce DEV/PROD (pre-ejecución)
- [ ] Confirmé entorno objetivo (`dev` o `prod`).
- [ ] Confirmé archivo env correcto.
- [ ] Confirmé `compose project` correcto.
- [ ] Confirmé que rutas a tocar pertenecen al árbol/allowlist.
- [ ] Confirmé que no hay credenciales de un entorno en otro.

