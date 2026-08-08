"""
Bothost должен запускать корневой main.py (HTTP + бот в одном процессе).

Этот файл оставлен как тонкий алиас на случай, если в панели указан bot/main.py.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT_MAIN = Path(__file__).resolve().parent.parent / "main.py"

if __name__ == "__main__":
    sys.argv[0] = str(ROOT_MAIN)
    runpy.run_path(str(ROOT_MAIN), run_name="__main__")
