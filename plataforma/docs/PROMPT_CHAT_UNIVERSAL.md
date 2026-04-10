# PROMPT DE CONTEXTO UNIVERSAL: MONSTRUO (DEV)
**Fecha Generacion:** 2026-04-01 15:08
**Objetivo:** Bootstrap operativo para iniciar agentes sin perder contexto ni cruzar DEV/PROD.

---

## 1. Mandato de este archivo
Este archivo es solo un **bootstrap**. No reemplaza la documentacion canonica.

Orden de autoridad obligatorio:
1. `plataforma/docs/PLAN_MAESTRO_MONSTRUO.md`
2. `plataforma/docs/PROYECTO_CONTEXTO.md`
3. `.agents/rules/reglas-monstruo-dev.md`
4. `plataforma/docs/ESTANDARES.md`
5. Instruccion puntual del usuario (si no contradice 1-4)

Hito mas reciente detectado:
- `2026-04-01 - DEV: raíz visible reservada para apps, shared core sale de gateway y soporte pasa a `plataforma``

---

## 2. Carga obligatoria al iniciar
Antes de proponer o ejecutar cambios, el agente debe cargar:
- `plataforma/docs/PLAN_MAESTRO_MONSTRUO.md`
- `plataforma/docs/PROYECTO_CONTEXTO.md`
- `.agents/rules/reglas-monstruo-dev.md`
- `plataforma/docs/ESTANDARES.md`
- `plataforma/docs/.README.md`
- `.README.md` de cada carpeta que vaya a tocar (allowlist local)

Frase de control recomendada:
`Contexto cargado: Plan + Contexto + Reglas DEV + Estandares + Allowlists`.

---

## 3. Separacion DEV/PROD (no negociable)
| Campo | DEV | PROD |
|---|---|---|
| Rama base | `dev` | `main` |
| Ruta servidor | `/srv/monstruo_dev` | `/srv/monstruo` |
| Env file | `plataforma/ops/env/.env.server.dev` | `plataforma/ops/env/.env.server` |
| Compose project | `monstruo_dev` | `monstruo` |
| Stack visible | `monstruo-dev` | `monstruo` |
| Puerto API interno | `9001` | `9000` |

Reglas duras:
- Prohibido mezclar `project` (`monstruo-dev` vs `monstruo_dev`).
- Prohibido usar env de PROD en tareas DEV.
- Prohibido desplegar a `main` sin autorizacion explicita del usuario.

---

## 4. Comandos de referencia vigentes
- Root: `/srv/monstruo_dev`
- Regenerar prompt universal:
```bash
python3 plataforma/ops/herramientas/deploy/generate_universal_prompt.py
```
- Verificar estructura:
```bash
python3 plataforma/ops/herramientas/deploy/verify_structure.py --root /srv/monstruo_dev
```
