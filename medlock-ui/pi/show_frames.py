"""Show the patient UI on the 2.8" LCD from pictures recorded on the Mac.

The Pi 3B is too slow to run Chromium, so pi/record_frames.py draws every
screen on the Mac and this script plays them back. Turning the knob moves
the highlight, pressing selects, exactly like the real UI. Results come from
the mock (pass by default), not the camera.

    python3 pi/show_frames.py --take-over                 # whole flow, knob
    python3 pi/show_frames.py --take-over --still pi/frames/pass/000.png
    python3 pi/show_frames.py --take-over --keys          # n / p / Enter in the terminal

Ctrl+C stops it and restarts the original home screen.
"""
import argparse
import json
import queue
import signal
import sys
import termios
import threading
import time
import tty
from pathlib import Path

from PIL import Image

FRAMES_DIR = Path(__file__).resolve().parent / 'frames'


def attach_knob(events, args):
    from gpiozero import Button, RotaryEncoder

    encoder = RotaryEncoder(args.knob_a, args.knob_b, max_steps=0)
    forward, backward = (lambda: events.put('next')), (lambda: events.put('prev'))
    encoder.when_rotated_clockwise = backward if args.reverse else forward
    encoder.when_rotated_counter_clockwise = forward if args.reverse else backward
    button = Button(args.knob_button, pull_up=not args.button_active_high, bounce_time=0.05)
    button.when_pressed = lambda: events.put('press')
    return encoder, button


def read_keys(events):
    """n / p / Enter from the terminal, as a stand-in for the knob."""
    keys = {'n': 'next', 'p': 'prev', '\r': 'press', '\n': 'press', ' ': 'press', 'q': 'quit'}
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    try:
        while True:
            action = keys.get(sys.stdin.read(1))
            if action:
                events.put(action)
            if action == 'quit':
                return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def main():
    p = argparse.ArgumentParser(description='Play the recorded MedLock screens on the 2.8" LCD')
    p.add_argument('--verdict', choices=['pass', 'fix', 'unable'], default='pass',
                   help='Which mock result "Check syringe" shows')
    p.add_argument('--still', type=Path, help='Just show this one picture (screen test)')
    p.add_argument('--repo', type=Path, default=Path.home() / 'MedLock', help='Team repo (for mirror_pi_display.py)')
    p.add_argument('--driver', type=Path, default=Path('/home/medlock/medlock_home.py'))
    p.add_argument('--take-over', action='store_true', help='Temporarily stop the home-screen program')
    p.add_argument('--knob-a', type=int, default=5)
    p.add_argument('--knob-b', type=int, default=6)
    p.add_argument('--knob-button', type=int, default=13)
    p.add_argument('--reverse', action='store_true', help='Swap knob turning direction')
    p.add_argument('--button-active-high', action='store_true', help='Knob press reads high instead of low')
    p.add_argument('--keys', action='store_true', help='Also take n / p / Enter from this terminal')
    p.add_argument('--no-knob', action='store_true', help='Do not use the knob')
    p.add_argument('--no-lcd', action='store_true', help='Do not use the LCD (testing)')
    p.add_argument('--save-frame', type=Path, help='Also save the shown picture as a PNG')
    args = p.parse_args()

    folder = FRAMES_DIR / args.verdict
    graph = None
    if not args.still:
        if not (folder / 'graph.json').exists():
            p.error(f'No recorded screens in {folder}. Run pi/record_frames.py on the Mac.')
        graph = json.loads((folder / 'graph.json').read_text())

    lcd = knob = None
    try:
        if not args.no_lcd:
            from lcd import Lcd
            lcd = Lcd(args.repo, args.driver, args.take_over)

        def show(path):
            frame = Image.open(path).convert('RGB')
            if lcd:
                lcd.show(frame)
            if args.save_frame:
                frame.save(args.save_frame)

        if args.still:
            show(args.still)
            print('Picture is on the little screen. Ctrl+C to stop.', flush=True)
            signal.pause()
            return

        events = queue.Queue()
        if not args.no_knob:
            knob = attach_knob(events, args)
        if args.keys:
            threading.Thread(target=read_keys, args=(events,), daemon=True).start()

        state = graph['start']
        show(folder / f'{state}.png')
        print('MedLock UI is on the little screen. Turn the knob to move, press to select.'
              + (' Keys: n = next, p = back, Enter = select, q = quit.' if args.keys else '')
              + ' Ctrl+C to stop.', flush=True)
        while True:
            action = events.get()
            if action == 'quit':
                return
            edges = graph['states'][state]
            if action not in edges:
                continue
            if f'{action}_via' in edges:  # the "Checking…" spinner screen
                show(folder / edges[f'{action}_via'])
                time.sleep(2)
            state = edges[action]
            show(folder / f'{state}.png')
    finally:
        if knob:
            for device in knob:
                device.close()
        if lcd:
            lcd.close()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt))
    try:
        main()
    except KeyboardInterrupt:
        print('Stopped.')
    except Exception as exc:
        print(f'MedLock screen demo stopped: {exc}', file=sys.stderr)
        sys.exit(1)
