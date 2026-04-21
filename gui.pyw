#!/usr/bin/env python3
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from gui_app.app import main


if __name__ == "__main__":
    raise SystemExit(main())
