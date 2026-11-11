"""
main.py - MedLock test harness / entry point

Modes:
    --auto   Scripted walkthrough of every state and error path (default in sim)
    --hw     Use real hardware (must run on Raspberry Pi)
    (no flag) Interactive menu driven by keyboard input

Keyboard shortcuts in interactive mode:
    i   simulate inserting the syringe
    r   simulate removing the syringe
    m   request a measurement
    a   acknowledge result / error
    s   print current status
    q   quit
"""

import argparse
import logging
import sys
import time
from typing import Optional

from .acquisition import Acquisition, Measurement
from .state_machine import StateMachine, State, Event


# ---------------------------------------------------------------- logging

def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)-12s %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------- callbacks

class ConsoleUI:
    """Minimal console stand-in for the TFT touchscreen."""

    def __init__(self):
        self._last_state: Optional[State] = None
        self._last_measurement: Optional[Measurement] = None

    def on_state_change(self, old: State, new: State):
        self._last_state = new
        arrow = f"{old.name:>9} -> {new.name:<9}"
        print(f"\n  [UI] {arrow}")

        if new is State.IDLE:
            print("       >>> Insert syringe")
        elif new is State.SEATED:
            print("       >>> Ready. Press M to measure.")
        elif new is State.MEASURING:
            print("       >>> Measuring...")
        elif new is State.RESULT and self._last_measurement:
            m = self._last_measurement
            air = "AIR DETECTED" if m.air_detected else "no air"
            print(f"       >>> RESULT: {m.volume_ml:.2f} mL, {air}")
            print("       >>> Press A to acknowledge.")
        elif new is State.ERROR and self._last_measurement:
            print(f"       >>> ERROR: {self._last_measurement.error}")
            print("       >>> Press A to acknowledge.")
        elif new is State.SHUTDOWN:
            print("       >>> Shutting down.")

    def on_measurement(self, m: Measurement):
        self._last_measurement = m


# ---------------------------------------------------------------- mock acquisition

class MockAcquisition(Acquisition):
    """
    Extends Acquisition so we can script seat state and measurements
    from the harness, without a Pi.

    Overrides:
        read_seat_sensor()  - returns self.mock_seated
        estimate_volume()   - returns self.mock_volume
        detect_air()        - returns self.mock_air
    """

    def __init__(self):
        super().__init__(simulate=True)
        self.mock_seated = False
        self.mock_volume: Optional[float] = 12.5
        self.mock_air: Optional[bool] = False
        self.raise_on_capture: Optional[Exception] = None

    def read_seat_sensor(self) -> bool:
        return self.mock_seated

    def capture_image(self):
        if self.raise_on_capture is not None:
            exc = self.raise_on_capture
            self.raise_on_capture = None
            raise exc
        # Return a dummy frame; algorithms are mocked below
        return object()

    def estimate_volume(self, image) -> Optional[float]:
        return self.mock_volume

    def detect_air(self, image) -> Optional[bool]:
        return self.mock_air


# ---------------------------------------------------------------- mode: interactive

def run_interactive(sm: StateMachine, acq: Acquisition):
    print("\nMedLock interactive test harness")
    print("Keys: i=insert r=remove m=measure a=ack s=status q=quit")
    print("(In simulation, seat insert/remove are driven by i/r keys.)")

    is_mock = isinstance(acq, MockAcquisition)
    if not is_mock:
        print("NOTE: running on real hardware - seat sensor is live;")
        print("      i/r keys only print a hint, they don't move hardware.")

    while True:
        # Let the state machine poll the seat sensor
        sm.tick()

        try:
            cmd = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if cmd == "q":
            break
        elif cmd == "i":
            if is_mock:
                acq.mock_seated = True
                print("  [harness] syringe inserted")
            else:
                print("  [harness] insert the physical syringe now")
        elif cmd == "r":
            if is_mock:
                acq.mock_seated = False
                print("  [harness] syringe removed")
            else:
                print("  [harness] remove the physical syringe now")
        elif cmd == "m":
            sm.request_measurement()
        elif cmd == "a":
            sm.acknowledge()
        elif cmd == "s":
            print(f"  [harness] state={sm.state.name}")
            if sm.last_measurement:
                m = sm.last_measurement
                print(f"  [harness] last: vol={m.volume_ml} "
                      f"air={m.air_detected} valid={m.valid} "
                      f"err={m.error}")
        else:
            print("  [harness] unknown command")

    sm.shutdown()


# ---------------------------------------------------------------- mode: auto

def run_auto(sm: StateMachine, acq: Acquisition):
    """
    Scripted walkthrough. Exercises every transition and every
    Acquisition failure mode. Prints a PASS/FAIL summary at the end.
    """
    if not isinstance(acq, MockAcquisition):
        print("--auto requires MockAcquisition (run in simulation)")
        return 1

    results = []

    def check(label: str, actual, expected):
        ok = actual == expected
        results.append((label, ok, actual, expected))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label:<45} "
              f"expected={expected!s:<18} actual={actual!s}")

    def settle(ticks: int = 3):
        """Run the state machine's tick a few times to register edges."""
        for _ in range(ticks):
            sm.tick()
            time.sleep(0.01)

    print("\n=== MedLock auto-test walkthrough ===\n")

    # --- 1. Boot: no syringe -------------------------------------------
    print("1. Boot with no syringe")
    settle()
    check("initial state", sm.state, State.IDLE)

    # --- 2. Insert syringe ---------------------------------------------
    print("\n2. Insert syringe")
    acq.mock_seated = True
    settle()
    check("after insert", sm.state, State.SEATED)

    # --- 3. Measure without pressing M ---------------------------------
    print("\n3. Confirm measure is gated by user request")
    check("still SEATED (no request)", sm.state, State.SEATED)

    # --- 4. Request measurement, success -------------------------------
    print("\n4. Request measurement (success path)")
    acq.mock_volume = 12.5
    acq.mock_air = False
    sm.request_measurement()
    check("after successful measure", sm.state, State.RESULT)
    check("volume recorded", sm.last_measurement.volume_ml, 12.5)
    check("air recorded", sm.last_measurement.air_detected, False)
    check("valid", sm.last_measurement.valid, True)

    # --- 5. Acknowledge, back to SEATED --------------------------------
    print("\n5. Acknowledge result")
    sm.acknowledge()
    check("after ack", sm.state, State.SEATED)

    # --- 6. Air-detected result ----------------------------------------
    print("\n6. Measure with air detected")
    acq.mock_air = True
    sm.request_measurement()
    check("state", sm.state, State.RESULT)
    check("air_detected", sm.last_measurement.air_detected, True)
    check("still valid", sm.last_measurement.valid, True)
    sm.acknowledge()

    # --- 7. Invalid measurement (volume None) --------------------------
    print("\n7. Measure with algorithm returning None volume")
    acq.mock_volume = None
    sm.request_measurement()
    check("state", sm.state, State.ERROR)
    check("valid", sm.last_measurement.valid, False)
    check("error msg present",
          sm.last_measurement.error is not None, True)
    sm.acknowledge()
    check("after ack from ERROR", sm.state, State.SEATED)

    # --- 8. Camera raises mid-capture ----------------------------------
    print("\n8. Measure with camera raising a real exception")
    acq.mock_volume = 10.0
    acq.mock_air = False
    acq.raise_on_capture = RuntimeError("simulated camera fault")
    sm.request_measurement()
    check("state", sm.state, State.ERROR)
    check("error mentions fault",
          "simulated camera fault" in (sm.last_measurement.error or ""),
          True)
    sm.acknowledge()

    # --- 9. Remove syringe mid-result ----------------------------------
    print("\n9. Remove syringe while in RESULT")
    acq.mock_volume = 8.0
    sm.request_measurement()
    check("in RESULT", sm.state, State.RESULT)
    acq.mock_seated = False
    settle()
    check("after removal", sm.state, State.IDLE)

    # --- 10. Measure gated when not seated -----------------------------
    print("\n10. Request measure while IDLE (not seated)")
    sm.request_measurement()
    check("stays IDLE", sm.state, State.IDLE)

    # --- 11. Re-insert, then shutdown ----------------------------------
    print("\n11. Re-insert, then shutdown")
    acq.mock_seated = True
    settle()
    check("back to SEATED", sm.state, State.SEATED)
    sm.shutdown()
    check("terminal state", sm.state, State.SHUTDOWN)

    # --- Summary --------------------------------------------------------
    passed = sum(1 for _, ok, _, _ in results if ok)
    total = len(results)
    print(f"\n=== {passed}/{total} checks passed ===\n")
    return 0 if passed == total else 1


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="MedLock test harness",
    )
    parser.add_argument("--hw", action="store_true",
                        help="use real hardware (Raspberry Pi)")
    parser.add_argument("--auto", action="store_true",
                        help="run scripted walkthrough, then exit")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="enable debug logging")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    if args.hw and args.auto:
        print("--hw and --auto are mutually exclusive", file=sys.stderr)
        return 2

    # --- construct acquisition ---
    if args.hw:
        acq: Acquisition = Acquisition(simulate=False)
    else:
        acq = MockAcquisition()

    acq.initialize()

    ui = ConsoleUI()
    sm = StateMachine(
        acq,
        on_state_change=ui.on_state_change,
        on_measurement=ui.on_measurement,
    )

    try:
        if args.auto:
            return run_auto(sm, acq)
        else:
            run_interactive(sm, acq)
            return 0
    finally:
        # Defensive: if run_* exited without shutdown
        if sm.state is not State.SHUTDOWN:
            sm.shutdown()
        acq.shutdown()


if __name__ == "__main__":
    sys.exit(main())