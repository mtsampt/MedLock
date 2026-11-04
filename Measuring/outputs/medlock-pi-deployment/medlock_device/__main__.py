import argparse
from pathlib import Path

from .runtime import Engine, PiCamera, ReplayCamera, Station
from .web import create_app


def main():
    p = argparse.ArgumentParser(description='MedLock inference-only station')
    p.add_argument('--bundle', type=Path, default=Path('outputs/pi-bundle'))
    p.add_argument('--replay', type=Path, help='Replay existing images instead of accessing a real camera')
    p.add_argument('--rotation', type=int, choices=[0, 90, 180, 270], default=0,
                   help='Counterclockwise rotation to put plunger top, tip bottom')
    p.add_argument('--port', type=int, default=8767)
    p.add_argument('--threads', type=int, choices=[1, 2, 3, 4], default=2)
    p.add_argument('--log', type=Path, default=Path('outputs/device-events.jsonl'))
    p.add_argument('--seat-pin', type=int, help='BCM input, active-low contact to ground; confirm wiring first')
    p.add_argument('--light-pin', type=int, help='BCM output, active-high driver input; never power LEDs directly')
    args = p.parse_args()
    if args.replay and (args.seat_pin is not None or args.light_pin is not None):
        p.error('Photo replay does not use GPIO. Omit the pin arguments.')
    if args.seat_pin is not None and args.seat_pin == args.light_pin:
        p.error('Seat and light must use different pins.')
    seat = light = None
    try:
        if args.seat_pin is not None or args.light_pin is not None:
            from gpiozero import Button, OutputDevice
            if args.seat_pin is not None:
                seat = Button(args.seat_pin, pull_up=True, bounce_time=.05)
            if args.light_pin is not None:
                light = OutputDevice(args.light_pin, active_high=True, initial_value=False)
        station = Station(Engine(args.bundle, args.threads),
                          ReplayCamera(args.replay) if args.replay else PiCamera(),
                          args.log, args.rotation, seat, light)
        create_app(station).run(host='127.0.0.1', port=args.port, threaded=True, use_reloader=False)
    finally:
        if light:
            light.off()
            light.close()
        if seat:
            seat.close()


if __name__ == '__main__':
    main()
