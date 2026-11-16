"""Runs the state machine live and publishes every change to the UI.

* A background thread calls `StateMachine.tick()` (seat polling) ~10x/second.
* Measurements run on a worker thread so HTTP requests never block.
* Every state change is pushed, as a full snapshot, to all subscribers
  (the server turns these into Server-Sent Events for the React UI).
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from medlock.acquisition import Acquisition, Measurement
from medlock.state_machine import State, StateMachine

logger = logging.getLogger(__name__)

AIR_ACTION = "Hold the syringe needle-up, tap it so the bubble rises, then push the air out."
RESEAT_ACTION = "Take the syringe out and press it fully into the dock."
RETRY_ACTION = "Try again. If it keeps happening, contact your clinic."


def to_ui_result(m: Optional[Measurement]) -> dict:
    """Translate a Measurement into the shape the React Result screen expects.

    Anything missing or invalid is "unable", never "pass".
    """
    if m is None:
        return {"verdict": "unable", "reason": "The station could not complete the check",
                "action": RETRY_ACTION, "volume_ml": None, "air_ml": None, "volume_checked": False}
    if not m.valid or m.air_detected is None:
        reason = m.error or "The station could not complete the check"
        action = RESEAT_ACTION if "seated" in reason.lower() else RETRY_ACTION
        return {"verdict": "unable", "reason": reason, "action": action,
                "volume_ml": None, "air_ml": None, "volume_checked": False}
    base = {"volume_ml": m.volume_ml, "air_ml": None,
            "volume_checked": m.volume_ml is not None,
            "air_score": (m.details or {}).get("air_score"), "timestamp": m.timestamp}
    if m.air_detected:
        return {**base, "verdict": "fix", "reason": "Air bubble detected", "action": AIR_ACTION}
    return {**base, "verdict": "pass", "reason": "No visible air detected.", "action": ""}


class Controller:
    def __init__(self, acquisition: Acquisition, *, sim_seat=None, poll_interval: float = 0.1):
        self.acq = acquisition
        self.sim_seat = sim_seat          # SimSeat or None (None = real GPIO seat)
        self.poll_interval = poll_interval

        self._lock = threading.RLock()    # serialises state-machine calls
        self._pub_lock = threading.Lock()  # guards revision + subscribers
        self._subs: set[queue.Queue] = set()
        self._revision = 0
        self._busy = False
        self._baseline: Optional[Measurement] = None
        self._result: Optional[dict] = None

        self.sm = StateMachine(acquisition, on_state_change=self._on_change)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        self.acq.initialize()
        self._thread = threading.Thread(target=self._loop, name="medlock-tick", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        with self._lock:
            self.sm.shutdown()
        self.acq.shutdown()

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_interval):
            try:
                with self._lock:
                    self.sm.tick()
            except Exception:
                logger.exception("tick failed")

    # ---- state machine callback -----------------------------------------
    def _on_change(self, old: State, new: State) -> None:
        # Runs inside the state machine, after last_measurement is assigned and
        # before on_measurement fires, so read the result from sm directly.
        if new in (State.RESULT, State.ERROR):
            m = self.sm.last_measurement
            if m is self._baseline:      # acquire() raised: no fresh reading
                m = None
            self._result = to_ui_result(m)
        elif new in (State.IDLE, State.SEATED, State.MEASURING):
            self._result = None
        self._publish()

    # ---- UI-facing actions ----------------------------------------------
    def request_measure(self) -> bool:
        with self._lock:
            if self.sm.state is not State.SEATED or self._busy:
                return False
            self._busy = True
        threading.Thread(target=self._measure_worker, name="medlock-measure", daemon=True).start()
        return True

    def _measure_worker(self) -> None:
        try:
            with self._lock:
                self._baseline = self.sm.last_measurement
                self.sm.request_measurement()
        except Exception:
            logger.exception("measurement worker failed")
        finally:
            self._busy = False

    def acknowledge(self) -> bool:
        with self._lock:
            if self.sm.state not in (State.RESULT, State.ERROR):
                return False
            self.sm.acknowledge()
            return True

    def set_sim_seat(self, seated: bool) -> bool:
        if self.sim_seat is None:
            return False
        self.sim_seat.set(seated)
        return True

    # ---- snapshots + pub/sub --------------------------------------------
    def snapshot(self) -> dict:
        state = self.sm.state
        with self._pub_lock:
            rev = self._revision
        return {
            "revision": rev,
            "state": state.name,
            "seated": state not in (State.IDLE, State.SHUTDOWN),
            "sim_seat": self.sim_seat is not None,
            "result": self._result if state in (State.RESULT, State.ERROR) else None,
        }

    def _publish(self) -> None:
        with self._pub_lock:
            self._revision += 1
        snap = self.snapshot()
        with self._pub_lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(snap)
            except queue.Full:            # slow client: drop its oldest, keep newest
                try:
                    q.get_nowait()
                    q.put_nowait(snap)
                except (queue.Empty, queue.Full):
                    pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=16)
        with self._pub_lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._pub_lock:
            self._subs.discard(q)
