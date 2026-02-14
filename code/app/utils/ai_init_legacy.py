from pathlib import Path
import sys

_pkg_dir = Path(__file__).resolve()
while _pkg_dir.name != "app" and _pkg_dir != _pkg_dir.parent:
    _pkg_dir = _pkg_dir.parent
if _pkg_dir.name == "app":
    _parent = _pkg_dir.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))

from app.core.ai.ai_init import init_ai_tables as _init_ai_tables

def main():
    return _init_ai_tables()

if __name__ == "__main__":
    raise SystemExit(main())
