#!/usr/bin/env python3
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[3]))
CTX_FILE = PROJECT_ROOT / "docs" / "PROYECTO_CONTEXTO.md"
OUT_FILE = PROJECT_ROOT / "docs" / "PROMPT_CHAT_UNIVERSAL.md"


def latest_hito(ctx_content: str) -> str:
    match = re.search(r"^## HITO:\s*(.+)$", ctx_content, flags=re.MULTILINE)
    return match.group(1).strip() if match else "Sin hito detectado"


def build_prompt(project_root: Path, hito: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""# PROMPT DE CONTEXTO UNIVERSAL: MONSTRUO (DEV)
**Fecha Generacion:** {now}
**Objetivo:** Bootstrap operativo para iniciar agentes sin perder contexto ni cruzar DEV/PROD.

---

## 1. Mandato de este archivo
Este archivo es solo un **bootstrap**. No reemplaza la documentacion canonica.

Orden de autoridad obligatorio:
1. `docs/PLAN_MAESTRO_MONSTRUO.md`
2. `docs/PROYECTO_CONTEXTO.md`
3. `.agents/rules/reglas-monstruo-dev.md`
4. `docs/ESTANDARES.md`
5. Instruccion puntual del usuario (si no contradice 1-4)

Hito mas reciente detectado:
- `{hito}`

---

## 2. Carga obligatoria al iniciar
Antes de proponer o ejecutar cambios, el agente debe cargar:
- `docs/PLAN_MAESTRO_MONSTRUO.md`
- `docs/PROYECTO_CONTEXTO.md`
- `.agents/rules/reglas-monstruo-dev.md`
- `docs/ESTANDARES.md`
- `docs/.README.md`
- `.README.md` de cada carpeta que vaya a tocar (allowlist local)

Frase de control recomendada:
`Contexto cargado: Plan + Contexto + Reglas DEV + Estandares + Allowlists`.

---

## 3. Separacion DEV/PROD (no negociable)
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
- Prohibido usar env de PROD en tareas DEV.
- Prohibido desplegar a `main` sin autorizacion explicita del usuario.

---

## 4. Comandos de referencia vigentes
- Root: `{project_root}`
- Regenerar prompt universal:
```bash
python3 ops/herramientas/deploy/generate_universal_prompt.py
```
- Verificar estructura:
```bash
python3 ops/herramientas/deploy/verify_structure.py --root {project_root}
```
"""


def main() -> None:
    if not CTX_FILE.exists():
        raise SystemExit(f"Error: no existe {CTX_FILE}")

    ctx_content = CTX_FILE.read_text(encoding="utf-8", errors="replace")
    prompt = build_prompt(PROJECT_ROOT, latest_hito(ctx_content))

    OUT_FILE.write_text(prompt.strip() + "\n", encoding="utf-8")
    print(f"Prompt universal generado en: {OUT_FILE}")


if __name__ == "__main__":
    main()
