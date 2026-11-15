"""
medlock - Capstone Design: syringe volume + air detection device.

Package layout:
    acquisition.py   - Hardware abstraction + measurement pipeline
    state_machine.py - Control policy: when to measure, how to recover
    main.py          - Test harness / entry point

Run the harness:
    python -m medlock.main            # simulation, interactive menu
    python -m medlock.main --auto     # simulation, scripted walkthrough
    python -m medlock.main --hw       # hardware mode (Raspberry Pi only)

Quick smoke test from Python:
    from medlock import Acquisition, StateMachine
"""

from .acquisition import Acquisition, Measurement
from .state_machine import StateMachine, State, Event

__all__ = [
    "Acquisition",
    "Measurement",
    "StateMachine",
    "State",
    "Event",
]

__version__ = "0.1.0"