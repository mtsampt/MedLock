"""Compatibility imports; the station controller now has an importable module.

Launch with python -m medlock_device from Measuring/, not this file.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'Measuring'))
from medlock_device.state_machine import FlowError, Session, load_protocol  # noqa: E402,F401
