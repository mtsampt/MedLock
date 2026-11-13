"""Use the rotary encoder as a backup for the touchscreen.

Turning the knob acts like Tab / Shift+Tab, so it moves the highlight
between buttons; pressing it acts like Enter, which taps the highlighted
button. Chromium sees an ordinary keyboard, so the UI needs no changes.

Find the pins first with find_pins.py, then (sudo is needed to create
the virtual keyboard):

    sudo python3 pi/knob.py --a 5 --b 6 --button 13

Add --reverse if turning clockwise moves the highlight backwards.
"""
import argparse
from signal import pause

from evdev import UInput, ecodes as e
from gpiozero import Button, RotaryEncoder

p = argparse.ArgumentParser(description='MedLock knob -> keyboard')
p.add_argument('--a', type=int, required=True, help='Encoder A / CLK pin (BCM)')
p.add_argument('--b', type=int, required=True, help='Encoder B / DT pin (BCM)')
p.add_argument('--button', type=int, help='Push switch / SW pin (BCM)')
p.add_argument('--reverse', action='store_true', help='Swap turning direction')
args = p.parse_args()

keyboard = UInput({e.EV_KEY: [e.KEY_TAB, e.KEY_LEFTSHIFT, e.KEY_ENTER]}, name='medlock-knob')


def tap(*keys):
    for k in keys:
        keyboard.write(e.EV_KEY, k, 1)
    keyboard.syn()
    for k in reversed(keys):
        keyboard.write(e.EV_KEY, k, 0)
    keyboard.syn()


forward = lambda: tap(e.KEY_TAB)
backward = lambda: tap(e.KEY_LEFTSHIFT, e.KEY_TAB)

encoder = RotaryEncoder(args.a, args.b, max_steps=0)
encoder.when_rotated_clockwise = backward if args.reverse else forward
encoder.when_rotated_counter_clockwise = forward if args.reverse else backward

if args.button is not None:
    button = Button(args.button, pull_up=True, bounce_time=0.05)
    button.when_pressed = lambda: tap(e.KEY_ENTER)

print('Knob ready. Ctrl+C to stop.')
pause()
