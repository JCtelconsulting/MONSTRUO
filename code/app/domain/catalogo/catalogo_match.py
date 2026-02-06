from pathlib import Path
import sys

_pkg_dir = Path(__file__).resolve()
while _pkg_dir.name != "backend" and _pkg_dir != _pkg_dir.parent:
    _pkg_dir = _pkg_dir.parent
if _pkg_dir.name == "backend":
    _parent = _pkg_dir.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))

from app.domain.catalogo.catalogo_match import *
