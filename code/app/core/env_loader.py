from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv


def _candidate_roots(start: Optional[Path]) -> Iterable[Path]:
    anchor = (start or Path(__file__)).resolve()
    if anchor.is_file():
        anchor = anchor.parent

    yield anchor
    for parent in anchor.parents:
        yield parent


def _default_candidates(root: Path) -> list[Path]:
    root_name = root.name.lower()
    is_dev_root = root_name.endswith("_dev") or root_name.endswith("-dev")

    canonical = [
        root / "ops" / "env" / ".env.server.dev",
        root / ".env.server.dev",
        root / "ops" / "env" / ".env.server",
        root / ".env.server",
    ]
    if not is_dev_root:
        canonical = [
            root / "ops" / "env" / ".env.server",
            root / ".env.server",
            root / "ops" / "env" / ".env.server.dev",
            root / ".env.server.dev",
        ]

    return canonical + [root / ".env"]


@lru_cache(maxsize=1)
def resolve_runtime_env_file(start: Optional[Path] = None) -> Optional[Path]:
    explicit_paths: list[str] = []
    for env_name in ("MONSTRUO_ENV_FILE", "ENV_FILE"):
        raw = str(os.getenv(env_name, "") or "").strip()
        if raw:
            explicit_paths.append(raw)

    for root in _candidate_roots(start):
        for raw in explicit_paths:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = (root / candidate).resolve()
            if candidate.exists():
                return candidate

        for candidate in _default_candidates(root):
            if candidate.exists():
                return candidate

    return None


def load_runtime_env(start: Optional[Path] = None, override: bool = False) -> Optional[Path]:
    env_file = resolve_runtime_env_file(start)
    if env_file:
        load_dotenv(env_file, override=override)
    return env_file
