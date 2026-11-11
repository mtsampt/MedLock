"""Read-only report of Pi touchscreen/input/SPI configuration; no pin changes."""
import os
from pathlib import Path


def read(path):
    try:return path.read_text().strip()
    except OSError:return '(unavailable)'


def main():
    print('=== INPUT DEVICES ===')
    events=sorted(Path('/sys/class/input').glob('event*'))
    if not events:print('No Linux input event devices found.')
    for event in events:
        device=Path('/dev/input')/event.name
        name=read(event/'device/name')
        print(f'{device}: {name} | readable={os.access(device,os.R_OK)}')
        print('  ABS capability bits:',read(event/'device/capabilities/abs'))
    print('\n=== SPI DEVICES ===')
    devices=sorted(Path('/sys/bus/spi/devices').glob('spi*'))
    if not devices:print('No SPI devices found.')
    for device in devices:
        driver=device/'driver'
        print(device.name,'driver='+ (driver.resolve().name if driver.exists() else '(none)'))
    print('\n=== DISPLAY / TOUCH BOOT SETTINGS ===')
    for path in [Path('/boot/firmware/config.txt'),Path('/boot/config.txt')]:
        if not path.exists():continue
        print(str(path))
        for line in read(path).splitlines():
            line=line.strip()
            if line.startswith('dtoverlay=') or (line.startswith('dtparam=') and 'spi' in line):
                print(' ',line)
    print('\nNo settings were changed. Send this output before choosing a touch device or GPIO pins.')


if __name__=='__main__':main()
