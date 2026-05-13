from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Sequence


def _portable_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _configure_portable_runtime() -> None:
    base_dir = _portable_base_dir()
    browser_dir = base_dir / "ms-playwright"
    if browser_dir.exists() and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)


def main(argv: Optional[Sequence[str]] = None) -> int:
    _configure_portable_runtime()
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--worker":
        from engine_api.worker import main as worker_main

        return worker_main(args[1:])
    from gui_app.app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
