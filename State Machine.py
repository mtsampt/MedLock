"""
state_machine.py - MedLock System State Machine

States flow:
    IDLE -> SEATED -> MEASURING -> RESULT -> IDLE

The seat sensor gates entry to MEASURING. Any error or unseating
returns the system to IDLE.
"""

from enum import Enum, auto
from typing import Callable, Optional
import logging

from acquisition import Acquisition, Measurement

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = auto()          # Waiting for syringe to be inserted
    SEATED = auto()        # Syringe detected, ready to measure
    MEASURING = auto()     # Capturing image + running algorithms
    RESULT = auto()        # Measurement available for display
    ERROR = auto()         # Recoverable fault; prompt user
    SHUTDOWN = auto()      # Terminal


class Event(Enum):
    SYRINGE_INSERTED = auto()
    SYRINGE_REMOVED = auto()
    MEASURE_REQUESTED = auto()
    MEASUREMENT_COMPLETE = auto()
    MEASUREMENT_FAILED = auto()
    ACKNOWLEDGE = auto()
    SHUTDOWN_REQUESTED = auto()


class StateMachine:
    """
    Drives the MedLock measurement flow.

    Call `tick()` periodically (e.g. 100 ms) from the main loop.
    The seat sensor is polled on every tick to detect insertion/removal.
    """

    # Poll interval between seat sensor checks (seconds)
    SEAT_POLL_INTERVAL = 0.1

    def __init__(
        self,
        acquisition: Acquisition,
        on_state_change: Optional[Callable[[State, State], None]] = None,
        on_measurement: Optional[Callable[[Measurement], None]] = None,
    ):
        self.acq = acquisition
        self.state = State.IDLE
        self.last_measurement: Optional[Measurement] = None
        self._on_state_change = on_state_change
        self._on_measurement = on_measurement
        self._seat_was_present = False

    # ---------- Transitions ----------

    def _transition(self, new_state: State):
        if new_state is self.state:
            return
        old = self.state
        self.state = new_state
        logger.info("State: %s -> %s", old.name, new_state.name)
        if self._on_state_change:
            try:
                self._on_state_change(old, new_state)
            except Exception:
                logger.exception("on_state_change callback failed")

    # ---------- Event handling ----------

    def handle(self, event: Event):
        if self.state is State.SHUTDOWN:
            return

        if event is Event.SHUTDOWN_REQUESTED:
            self._transition(State.SHUTDOWN)
            return

        # --- Global: syringe removal forces IDLE from any non-terminal state ---
        if event is Event.SYRINGE_REMOVED and self.state in (
            State.SEATED, State.MEASURING, State.RESULT, State.ERROR
        ):
            self._transition(State.IDLE)
            return

        # --- State-specific handling ---
        if self.state is State.IDLE:
            if event is Event.SYRINGE_INSERTED:
                self._transition(State.SEATED)

        elif self.state is State.SEATED:
            if event is Event.MEASURE_REQUESTED:
                self._transition(State.MEASURING)
                self._do_measurement()

        elif self.state is State.RESULT:
            if event is Event.ACKNOWLEDGE:
                self._transition(State.SEATED if self._seat_present() else State.IDLE)

        elif self.state is State.ERROR:
            if event is Event.ACKNOWLEDGE:
                self._transition(State.SEATED if self._seat_present() else State.IDLE)

    # ---------- Main loop hook ----------

    def tick(self):
        """Call from the main loop. Handles sensor-driven events."""
        if self.state is State.SHUTDOWN:
            return

        present = self._seat_present()

        if present and not self._seat_was_present:
            # Edge: syringe just inserted
            self.handle(Event.SYRINGE_INSERTED)
        elif not present and self._seat_was_present:
            # Edge: syringe just removed
            self.handle(Event.SYRINGE_REMOVED)

        self._seat_was_present = present

    def _seat_present(self) -> bool:
        try:
            return self.acq.read_seat_sensor()
        except Exception:
            logger.exception("Seat sensor read failed")
            return False

    # ---------- Measurement execution ----------

    def _do_measurement(self):
        # Re-check seating immediately before capture
        if not self._seat_present():
            self._transition(State.IDLE)
            return

        try:
            measurement = self.acq.acquire()
        except Exception:
            logger.exception("Acquisition raised unexpectedly")
            self._transition(State.ERROR)
            return

        self.last_measurement = measurement

        if measurement.valid:
            self._transition(State.RESULT)
            if self._on_measurement:
                try:
                    self._on_measurement(measurement)
                except Exception:
                    logger.exception("on_measurement callback failed")
        else:
            logger.warning("Measurement invalid: %s", measurement.error)
            self._transition(State.ERROR)

    # ---------- Convenience ----------

    def request_measurement(self):
        """Called by UI when user presses 'Measure'."""
        self.handle(Event.MEASURE_REQUESTED)

    def acknowledge(self):
        """Called by UI after result/error has been seen."""
        self.handle(Event.ACKNOWLEDGE)

    def shutdown(self):
        self.handle(Event.SHUTDOWN_REQUESTED)
