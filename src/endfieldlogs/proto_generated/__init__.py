from __future__ import annotations

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_THIS_DIR_STR = str(_THIS_DIR)
if _THIS_DIR_STR not in sys.path:
    sys.path.insert(0, _THIS_DIR_STR)
