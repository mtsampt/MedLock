import argparse
import logging
import signal
import threading
from pathlib import Path

from .runtime import Engine, PiCamera, ReplayCamera, Station
from .web import create_app
from .state_machine import Session, load_protocol
from .volume import VolumeEstimator
from .seat import SeatSensor


def main():
    p = argparse.ArgumentParser(description='MedLock inference-only station')
    root = Path(__file__).resolve().parents[1]
    p.add_argument('--bundle', type=Path, default=root/'outputs/pi-bundle')
    p.add_argument('--ui-dir', type=Path, default=(root.parent/'medlock-ui/dist' if (root.parent/'medlock-ui').exists() else Path(__file__).with_name('ui')))
    p.add_argument('--protocol', type=Path, help='Bench protocol JSON; defaults to bundled prototype')
    p.add_argument('--volume-calibration', type=Path)
    p.add_argument('--setup-id', help='Must match the calibrated syringe/dock/camera setup')
    p.add_argument('--replay', type=Path, help='Replay existing images instead of accessing a real camera')
    p.add_argument('--rotation', type=int, choices=[0, 90, 180, 270], default=0,
                   help='Counterclockwise rotation to put plunger top, tip bottom')
    p.add_argument('--port', type=int, default=8767)
    p.add_argument('--threads', type=int, choices=[1, 2, 3, 4], default=2)
    p.add_argument('--capture-dir', type=Path, help='Optional raw capture archive for independent bench trials')
    p.add_argument('--log', type=Path, default=root/'runtime/device-events.jsonl')
    p.add_argument('--hardware-profile', choices=['rev0'], help='Report Rev0: seat GPIO17 HIGH, backlight GPIO18')
    p.add_argument('--seat-pin', type=int, help='BCM input; Rev0 optical seat is GPIO17, active HIGH')
    p.add_argument('--seat-active', choices=['high', 'low'], default='high')
    p.add_argument('--seat-pull', choices=['external', 'up', 'down'], default='external')
    p.add_argument('--light-pin', type=int, help='BCM output, active-high driver input; never power LEDs directly')
    p.add_argument('--display', choices=['browser','ili9341'], default='browser')
    p.add_argument('--display-cs', type=int, help='ILI9341 chip select, BCM number')
    p.add_argument('--display-dc', type=int, help='ILI9341 data/command, BCM number')
    p.add_argument('--display-reset', type=int, help='ILI9341 reset, BCM number')
    p.add_argument('--display-rotation', type=int, choices=[90,270], default=90)
    p.add_argument('--touch-device', type=Path, help='Configured Linux ADS7846/XPT2046 /dev/input/eventX')
    p.add_argument('--touch-swap', action='store_true')
    p.add_argument('--touch-invert-x', action='store_true')
    p.add_argument('--touch-invert-y', action='store_true')
    p.add_argument('--encoder-a', type=int)
    p.add_argument('--encoder-b', type=int)
    p.add_argument('--encoder-switch', type=int)
    args = p.parse_args()
    encoder_pins = [args.encoder_a, args.encoder_b, args.encoder_switch]
    if any(pin is not None for pin in encoder_pins) and any(pin is None for pin in encoder_pins):
        p.error('Encoder requires --encoder-a, --encoder-b and --encoder-switch together.')
    if args.hardware_profile == 'rev0':
        if args.seat_pin not in (None, 17) or args.light_pin not in (None, 18) or args.seat_active != 'high' or args.seat_pull != 'external':
            p.error('Rev0 profile requires GPIO17 active HIGH/external pull and GPIO18 backlight.')
        args.seat_pin, args.light_pin = 17, 18
    if args.replay and (args.seat_pin is not None or args.light_pin is not None):
        p.error('Photo replay does not use GPIO. Omit the pin arguments.')
    if any(pin is not None and not 0 <= pin <= 27 for pin in (args.seat_pin, args.light_pin)):
        p.error('Seat/light pins must use BCM numbers 0–27.')
    controlled = [pin for pin in [args.seat_pin, args.light_pin, *encoder_pins] if pin is not None]
    if len(set(controlled)) != len(controlled) or any(not 0 <= pin <= 27 for pin in controlled):
        p.error('GPIO control pins must be distinct BCM numbers 0–27.')
    if args.display=='ili9341':
        pins=[args.display_cs,args.display_dc,args.display_reset]
        if None in pins or args.touch_device is None:
            p.error('Native display needs --display-cs, --display-dc, --display-reset and --touch-device. Confirm wiring first.')
        all_pins=pins+controlled
        if len(set(all_pins))!=len(all_pins) or any(pin in {9,10,11} or not 0<=pin<=27 for pin in all_pins):
            p.error('Use distinct BCM control pins; reserve SPI0 pins 9, 10 and 11 for the bus.')
    protocol = load_protocol(args.protocol)
    volume = VolumeEstimator(args.volume_calibration, args.setup_id) if args.volume_calibration else None
    if volume is not None:
        c = volume.calibration
        if c['rotation'] != args.rotation:
            p.error('Rotation must match volume calibration.')
        target, tolerance = protocol.get('target_volume_ml'), protocol.get('tolerance_ml')
        if tolerance is not None and (tolerance < c['max_error_ml'] or not c['volume_range_ml'][0] <= target - tolerance < target + tolerance <= c['volume_range_ml'][1]):
            p.error('Target/tolerance must fit inside calibrated range and tolerance must cover calibration error.')
    if not args.replay and args.seat_pin is None:
        p.error('Hardware mode requires --seat-pin. Use --replay for simulated seating.')
    seat = light = session = server = encoder = None
    encoder_thread = thread = None
    server_failed = threading.Event()
    stop = threading.Event()
    previous_signals = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_signals[sig] = signal.signal(sig, lambda *_: stop.set())
    try:
        if args.seat_pin is not None or args.light_pin is not None:
            from gpiozero import OutputDevice
            if args.seat_pin is not None:
                seat = SeatSensor(args.seat_pin, args.seat_active, args.seat_pull)
            if args.light_pin is not None:
                light = OutputDevice(args.light_pin, active_high=True, initial_value=False)
        station = Station(Engine(args.bundle, args.threads),
                          ReplayCamera(args.replay) if args.replay else PiCamera(),
                          args.log, args.rotation, seat, light, volume, args.capture_dir)
        session = Session(station, protocol)
        if args.encoder_a is not None:
            from .encoder import EncoderInput
            encoder = EncoderInput(*encoder_pins, session=session)
            encoder_thread = threading.Thread(target=encoder.run, args=(session, stop), daemon=True)
            encoder_thread.start()
        from waitress import create_server
        server = create_server(create_app(station, session, args.ui_dir), host='127.0.0.1', port=args.port, threads=4)
        def run_server():
            try:
                server.run()
            except Exception:
                # Closing listener/trigger sockets can interrupt the polling loop.
                if not stop.is_set():
                    logging.exception('Local API server failed.')
                    server_failed.set()
            finally:
                if not stop.is_set():
                    server_failed.set()
                    stop.set()
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        print(f'MedLock {station.camera.mode}: http://127.0.0.1:{args.port}/', flush=True)
        if args.display=='ili9341':
            from .display_hardware import run_native
            run_native(session,args,stop)
        else:
            while not stop.wait(.2):
                if not thread.is_alive():
                    raise RuntimeError('Local API server stopped unexpectedly.')
        if server_failed.is_set():
            raise RuntimeError('Local API server stopped unexpectedly.')
    finally:
        stop.set()
        if server is not None:
            server.close()
            server.task_dispatcher.shutdown()
        if thread is not None:
            thread.join(timeout=2)
        if encoder_thread is not None:
            encoder_thread.join(timeout=2)
        try:
            if encoder is not None:
                encoder.close()
        finally:
            if session is not None:
                session.close()
        if session is None:
            try:
                if light is not None:
                    light.off()
            finally:
                for resource in (light, seat):
                    if resource is not None:
                        resource.close()
        for sig, previous in previous_signals.items():
            signal.signal(sig, previous)


if __name__ == '__main__':
    main()
