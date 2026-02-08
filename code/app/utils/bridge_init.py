from pathlib import Path
import sys

_pkg_dir = Path(__file__).resolve()
while _pkg_dir.name != "app" and _pkg_dir != _pkg_dir.parent:
    _pkg_dir = _pkg_dir.parent
if _pkg_dir.name == "app":
    _parent = _pkg_dir.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))

from app.core.ai.bridge import main as _bridge_main

def main():
    return _bridge_main()

if __name__ == "__main__":
    raise SystemExit(main())
