from __future__ import annotations

import sys
from typing import Optional, Sequence

from engine_api.worker import main as worker_main
from gui_app.app import main as gui_main


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--worker":
        return worker_main(args[1:])
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
