"""MedLock integrated station.

Glues the three team components together without moving any of them:

    Acquisition and State Machine/medlock/   -> Acquisition, StateMachine
    Measuring/medlock_device + medlock_lab/  -> camera, model, Station.check()
    medlock-ui/                              -> React screens (served from dist/)

The two Python component folders are not importable by default (one has spaces
in its name), so this bootstrap puts them on sys.path.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for _p in (ROOT / "Acquisition and State Machine", ROOT / "Measuring"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
