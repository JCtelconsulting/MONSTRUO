#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CODE_DIR = PROJECT_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app.core.ai import ai_local_openai_compat


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight de IA para taxonomia/catalogo")
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Ademas del status, intenta una llamada simple de chat",
    )
    args = parser.parse_args()

    status = ai_local_openai_compat.check_status()
    print("AI status:")
    print(json.dumps(status, ensure_ascii=False, indent=2))

    if not args.chat:
        return 0

    reply = ai_local_openai_compat.chat(
        [
            {"role": "system", "content": "Responde en una linea."},
            {"role": "user", "content": "Prueba de conectividad para catalogo"},
        ],
        temperature=0.0,
    )

    if reply is None:
        print("Chat de prueba: FAIL")
        return 2

    print("Chat de prueba: OK")
    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
