#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent


def _relaunch_with_local_venv() -> None:
    if getattr(sys, "frozen", False):
        return

    scripts_dir = project_root / ".venv" / "Scripts"
    local_python = scripts_dir / "python.exe"
    local_pythonw = scripts_dir / "pythonw.exe"
    if not local_python.exists():
        return

    current = Path(sys.executable).resolve()
    if current in {local_python.resolve(), local_pythonw.resolve()}:
        return

    target = local_pythonw if local_pythonw.exists() else local_python
    subprocess.Popen(
        [str(target), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(project_root),
    )
    raise SystemExit(0)


_relaunch_with_local_venv()
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from gui_app.app import main


if __name__ == "__main__":
    raise SystemExit(main())
