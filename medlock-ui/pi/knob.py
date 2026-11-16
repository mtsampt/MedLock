"""Rotary controls shared by browser-keyboard and measuring LCD modes.

Standalone use creates a virtual keyboard for Chromium (requires sudo):
    sudo python3 pi/knob.py --a 5 --b 6 --button 13
The measuring LCD bridge imports attach_controls directly; it needs no
virtual keyboard or evdev. Do not run both readers on the same pins.
"""
import argparse
from signal import pause


def attach_controls(emit, a=5, b=6, button=13, reverse=False, button_active_high=False):
    """Emit next/prev/press through a callback; return owned GPIO devices."""
    from gpiozero import Button, RotaryEncoder
    pins = [a,b]+([] if button is None else [button])
    if len(set(pins)) != len(pins) or any(not 0 <= pin <= 27 for pin in pins):
        raise ValueError('Use distinct BCM GPIO numbers from 0 through 27.')
    encoder = switch = None
    try:
        encoder = RotaryEncoder(a,b,max_steps=0)
        encoder.when_rotated_clockwise = lambda: emit('prev' if reverse else 'next')
        encoder.when_rotated_counter_clockwise = lambda: emit('next' if reverse else 'prev')
        if button is not None:
            switch = Button(button,pull_up=not button_active_high,bounce_time=.05)
            switch.when_pressed = lambda: emit('press')
        return tuple(device for device in (encoder,switch) if device is not None)
    except Exception:
        for device in (switch,encoder):
            if device is not None:device.close()
        raise


def main():
    parser = argparse.ArgumentParser(description='MedLock knob -> browser keyboard')
    parser.add_argument('--a',type=int,required=True,help='Encoder A / CLK (BCM)')
    parser.add_argument('--b',type=int,required=True,help='Encoder B / DT (BCM)')
    parser.add_argument('--button',type=int,help='Push switch / SW (BCM)')
    parser.add_argument('--reverse',action='store_true')
    parser.add_argument('--button-active-high',action='store_true')
    args = parser.parse_args()
    from evdev import UInput, ecodes as e
    keyboard = UInput({e.EV_KEY:[e.KEY_TAB,e.KEY_LEFTSHIFT,e.KEY_ENTER]},name='medlock-knob')
    devices = ()
    try:
        def emit(action):
            keys = {'next':(e.KEY_TAB,), 'prev':(e.KEY_LEFTSHIFT,e.KEY_TAB),
                    'press':(e.KEY_ENTER,)}[action]
            for key in keys:keyboard.write(e.EV_KEY,key,1)
            keyboard.syn()
            for key in reversed(keys):keyboard.write(e.EV_KEY,key,0)
            keyboard.syn()
        devices = attach_controls(emit,args.a,args.b,args.button,args.reverse,args.button_active_high)
        print('Knob ready. Ctrl+C to stop.',flush=True)
        pause()
    finally:
        for device in devices:device.close()
        keyboard.close()


if __name__=='__main__':
    import signal
    signal.signal(signal.SIGTERM,lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:main()
    except KeyboardInterrupt:pass
