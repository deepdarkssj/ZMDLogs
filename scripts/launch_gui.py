from __future__ import annotations

import sys

from endfieldlogs.cli import main


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("gui")
    raise SystemExit(main())
