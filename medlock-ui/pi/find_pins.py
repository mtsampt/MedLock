"""Find which GPIO pins the knob (rotary encoder) is wired to.

Run on the Pi, then turn the knob slowly and press it:

    python3 pi/find_pins.py

Every pin that changes is printed. Turning makes two pins flicker (the
encoder's A and B); pressing makes one pin go low (the push switch).
Pins already used by something else (SPI, a running display program) are
skipped. Stop the team's display program before running this.
"""
import time

from gpiozero import DigitalInputDevice

# BCM number -> physical header pin
PHYSICAL = {2: 3, 3: 5, 4: 7, 5: 29, 6: 31, 7: 26, 8: 24, 9: 21, 10: 19, 11: 23, 12: 32, 13: 33,
            14: 8, 15: 10, 16: 36, 17: 11, 18: 12, 19: 35, 20: 38, 21: 40, 22: 15, 23: 16,
            24: 18, 25: 22, 26: 37, 27: 13}

pins = {}
for bcm in PHYSICAL:
    try:
        pins[bcm] = DigitalInputDevice(bcm, pull_up=True)
    except Exception:
        pass  # in use by a driver or another program

print('Watching GPIO', ', '.join(map(str, pins)))
print('Skipped (in use):', ', '.join(str(b) for b in PHYSICAL if b not in pins) or 'none')
print('Turn the knob slowly, then press it. Ctrl+C to stop.\n')

last = {bcm: dev.value for bcm, dev in pins.items()}
counts = {bcm: 0 for bcm in pins}
try:
    while True:
        for bcm, dev in pins.items():
            value = dev.value
            if value != last[bcm]:
                last[bcm] = value
                counts[bcm] += 1
                print(f'GPIO {bcm:>2} (physical pin {PHYSICAL[bcm]:>2}) -> {"high" if value else "LOW"}')
        time.sleep(0.002)
except KeyboardInterrupt:
    changed = {b: n for b, n in counts.items() if n}
    print('\nPins that changed (GPIO: times):', changed or 'none')
