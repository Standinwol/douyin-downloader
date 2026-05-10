from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_command(extra_args: Sequence[str] = ()) -> List[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "DouyinDownloader",
        "--hidden-import",
        "engine_api.worker",
        "--hidden-import",
        "engine_api.service",
        "--hidden-import",
        "gui_app.launcher",
        "--collect-submodules",
        "gmssl",
        str(PROJECT_ROOT / "gui_app" / "launcher.py"),
        *extra_args,
    ]


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "PyInstaller is not installed. Run: python -m pip install .[desktop]",
            file=sys.stderr,
        )
        return 1

    command = build_command(argv or [])
    completed = subprocess.run(command, cwd=str(PROJECT_ROOT), check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
