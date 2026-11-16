"""Run the integrated MedLock station.

    python -m station --bundle ... [--replay DIR | camera] [--seat-pin N]

Then open http://127.0.0.1:8770/ in the Pi's browser (kiosk mode).
"""
import argparse
import logging
from pathlib import Path

from . import ROOT
from .controller import Controller
from .measuring_acquisition import MeasuringAcquisition, SimSeat
from .server import create_app


def main(argv=None):
    p = argparse.ArgumentParser(description="MedLock integrated station")
    p.add_argument("--bundle", type=Path, default=ROOT / "Measuring/outputs/pi-bundle")
    p.add_argument("--replay", type=Path, help="Replay saved photos instead of the Pi camera")
    p.add_argument("--rotation", type=int, choices=[0, 90, 180, 270], default=None,
                   help="Counterclockwise rotation to put plunger top, tip bottom. "
                        "Default: 90 for the Pi camera mount, 0 for --replay photos.")
    p.add_argument("--threads", type=int, choices=[1, 2, 3, 4], default=2)
    p.add_argument("--port", type=int, default=8770)
    p.add_argument("--seat-pin", type=int, help="BCM input for the seat sensor. Omit to simulate seating.")
    p.add_argument("--seat-active-high", action="store_true",
                   help="Seat sensor is HIGH when seated (default: LOW, contact to ground). "
                        "Confirm HALL_OUT polarity on your board first.")
    p.add_argument("--light-pin", type=int, help="BCM output to a LED driver; never power LEDs directly")
    p.add_argument("--poll", type=float, default=0.1, help="Seat poll interval, seconds")
    p.add_argument("--ui-dir", type=Path, default=ROOT / "medlock-ui/dist")
    p.add_argument("--log", type=Path, default=ROOT / "Measuring/outputs/device-events.jsonl")
    p.add_argument("--ui-log", type=Path, default=ROOT / "Measuring/outputs/ui-events.jsonl")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    if args.replay and (args.seat_pin is not None or args.light_pin is not None):
        p.error("Photo replay does not use GPIO. Omit the pin arguments.")
    if args.seat_pin is not None and args.seat_pin == args.light_pin:
        p.error("Seat and light must use different pins.")

    if args.rotation is None:
        args.rotation = 0 if args.replay else 90

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)-14s %(message)s", datefmt="%H:%M:%S")

    # Imported here so --help works on machines without cv2/onnx.
    from medlock_device.runtime import Engine, PiCamera, ReplayCamera, Station

    seat = light = None
    try:
        if args.seat_pin is not None or args.light_pin is not None:
            from gpiozero import Button, OutputDevice
            if args.seat_pin is not None:
                seat = Button(args.seat_pin, pull_up=not args.seat_active_high, bounce_time=.05)
            if args.light_pin is not None:
                light = OutputDevice(args.light_pin, active_high=True, initial_value=False)

        station = Station(Engine(args.bundle, args.threads),
                          ReplayCamera(args.replay) if args.replay else PiCamera(),
                          args.log, args.rotation, seat, light)

        sim = None if seat is not None else SimSeat()
        reader = (lambda: seat.is_pressed) if seat is not None else (lambda: sim.seated)
        controller = Controller(MeasuringAcquisition(station, reader),
                                sim_seat=sim, poll_interval=args.poll)
        controller.start()
        print(f"MedLock station: http://127.0.0.1:{args.port}/   "
              f"(seat: {'GPIO' if seat else 'simulated'}, camera: {station.camera.mode})")
        try:
            create_app(controller, args.ui_dir, args.ui_log).run(
                host="127.0.0.1", port=args.port, threaded=True, use_reloader=False)
        finally:
            controller.stop()
    finally:
        if light:
            light.off()
            light.close()
        if seat:
            seat.close()


if __name__ == "__main__":
    main()
