"""Acquisition backed by the Measuring component.

The state machine only knows about `Acquisition`. This subclass makes that
interface real by delegating to Measuring's `Station.check()`, which already
handles the light, camera capture, image-quality gate, air classifier, seat
re-checks during capture, locking and the JSONL event log.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from medlock.acquisition import Acquisition, Measurement

logger = logging.getLogger(__name__)


class SimSeat:
    """Stand-in for the seat sensor when no GPIO pin is configured."""

    def __init__(self, seated: bool = False):
        self._seated = seated
        self._lock = threading.Lock()

    @property
    def seated(self) -> bool:
        with self._lock:
            return self._seated

    def set(self, seated: bool) -> None:
        with self._lock:
            self._seated = bool(seated)


class MeasuringAcquisition(Acquisition):
    # Volume measurement is unfinished, so an air-only reading is valid.
    require_volume = False

    def __init__(self, station, seat_reader: Callable[[], bool]):
        super().__init__(simulate=station.seat is None)
        self.station = station
        self._seat_reader = seat_reader

    # --- seat -----------------------------------------------------------
    def read_seat_sensor(self) -> bool:
        return bool(self._seat_reader())

    # --- volume hook ----------------------------------------------------
    def estimate_volume(self, image) -> Optional[float]:
        """Hook for the volume algorithm.

        `image` is the cleaned barrel crop (PIL image) from the measurement
        that just ran. Return millilitres, or None while volume is unfinished.
        """
        return None

    # --- full measurement -----------------------------------------------
    def acquire(self) -> Measurement:
        ts = datetime.now(timezone.utc).isoformat()
        try:
            if not self.read_seat_sensor():
                return Measurement(None, None, False, False, ts, error="Syringe not seated")

            # The state machine just confirmed seating. With a GPIO seat the
            # Station re-reads the pin itself during capture; in simulation it
            # uses the value passed here.
            result, code = self.station.check(True)
            state = result.get("state")

            if state not in ("air_detected", "no_air_detected"):
                # "unable" / "busy": Station's message is already patient-facing.
                msg = result.get("message") or "Measurement failed"
                seat_problem = any(w in msg.lower() for w in ("seated", "moved"))
                return Measurement(None, None, not seat_problem, False, ts,
                                   error=msg, details={"station": result})

            volume = self.estimate_volume(getattr(self.station, "preview", None))
            valid = volume is None or volume >= 0
            return Measurement(
                volume_ml=volume,
                air_detected=(state == "air_detected"),
                syringe_seated=True,
                valid=valid,
                timestamp=ts,
                error=None if valid else "Incomplete measurement",
                details={
                    "air_score": result.get("air_score"),
                    "label": result.get("label"),
                    "model_version": result.get("model_version"),
                    "inference_ms": result.get("inference_ms"),
                    "elapsed_ms": result.get("elapsed_ms"),
                    "source": result.get("source"),
                },
            )
        except Exception as exc:  # never let hardware errors escape into the state machine
            logger.exception("Acquisition failed")
            return Measurement(None, None, False, False, ts, error=f"Acquisition failed: {exc}")
