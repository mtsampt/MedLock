"""Launch the native touchscreen replay demo, remembering this Pi's wiring."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def validate(settings):
    pins = [settings[key] for key in ('cs', 'dc', 'reset')]
    if any(type(pin) is not int or not 0 <= pin <= 27 or pin in {9, 10, 11} for pin in pins):
        raise ValueError('Use BCM pins 0–27; pins 9, 10 and 11 are reserved for SPI.')
    if len(set(pins)) != 3:
        raise ValueError('CS, DC and RESET must use different BCM pins.')
    if not isinstance(settings['touch'], str) or not settings['touch'].strip():
        raise ValueError('Enter the full touch input device path.')
    if not Path(settings['touch']).is_absolute() or not Path(settings['touch']).exists():
        raise ValueError('Touch input device path does not exist on this Pi.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure', action='store_true', help='Enter the screen wiring again')
    args = parser.parse_args()
    measuring = Path(__file__).resolve().parents[1]
    config = measuring / 'runtime' / 'touchscreen.json'
    try:
        if config.exists() and not args.configure:
            settings = json.loads(config.read_text())
            validate(settings)
        else:
            print('Enter the confirmed wiring for your ILI9341 screen (BCM numbers).')
            settings = {
                'cs': int(input('LCD CS BCM pin: ').strip()),
                'dc': int(input('LCD DC BCM pin: ').strip()),
                'reset': int(input('LCD RESET BCM pin: ').strip()),
                'touch': input('Full touch input path, e.g. /dev/input/event0: ').strip(),
            }
            validate(settings)
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(json.dumps(settings, indent=2) + '\n')
    except (ValueError, KeyError, TypeError, OSError, EOFError) as exc:
        parser.exit(1, f'Screen configuration: {exc}\nRun again with --configure to enter the wiring.\n')

    python = next((path for path in (
        measuring / '.venv' / 'bin' / 'python',
        measuring.parent / '.venv' / 'bin' / 'python',
    ) if path.is_file() and os.access(path, os.X_OK)), Path(sys.executable))
    os.chdir(measuring)
    command = [str(python), '-m', 'medlock_device',
               '--replay', str(measuring / 'outputs' / 'medlock-pilot-2026-10-21' / 'images'),
               '--display', 'ili9341',
               '--display-cs', str(settings['cs']),
               '--display-dc', str(settings['dc']),
               '--display-reset', str(settings['reset']),
               '--touch-device', settings['touch']]
    print('Starting the small-screen demo with saved syringe photos.', flush=True)
    os.execv(str(python), command)


if __name__ == '__main__':
    main()
