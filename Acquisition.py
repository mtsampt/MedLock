"""Compatibility imports. Run the unified station from Measuring/.

Implementation: Measuring/medlock_device/acquisition.py and measurement.py.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'Measuring'))
from medlock_device.acquisition import Acquisition  # noqa: E402,F401
from medlock_device.measurement import Measurement  # noqa: E402,F401
