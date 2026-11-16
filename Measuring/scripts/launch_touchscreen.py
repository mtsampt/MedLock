"""Shortcut for the existing Pi display bridge, using its known screen setup."""
from __future__ import annotations

import os
from pathlib import Path
import sys


def main():
    measuring = Path(__file__).resolve().parents[1]
    python = next((path for path in (
        measuring / '.venv' / 'bin' / 'python',
        measuring.parent / '.venv' / 'bin' / 'python',
    ) if path.is_file() and os.access(path, os.X_OK)), Path(sys.executable))
    os.chdir(measuring)
    command = [str(python), str(measuring / 'scripts' / 'mirror_pi_display.py'),
               '--start-app', '--take-over', '--replay', *sys.argv[1:]]
    os.execv(str(python), command)


if __name__ == '__main__':
    main()
