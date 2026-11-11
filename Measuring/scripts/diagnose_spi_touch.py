"""Read raw REV B XPT2046 values without calibration or touch filtering.

Stop mirror_pi_display.py before running. Uses only SPI0.1; does not write
boot settings, claim GPIO pins, change wiring, or send commands to the LCD.
"""
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from medlock_device.spi_touch import read_burst
from statistics import median


def main():
    import spidev
    path = Path(__file__).resolve().parents[1]/'outputs/touch-diagnostic.txt'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w') as log:
        def report(line):
            print(line,flush=True)
            log.write(line+'\n')
            log.flush()
        report('MedLock touch diagnostic v2: continuous-CS powered ADC burst')
        report('SPI0.1 / BCM7 chip select / 500 kHz / mode0')
        report('Raw readings only. The little screen will not change during this check.')
        spi = spidev.SpiDev()
        try:
            spi.open(0,1)
            spi.max_speed_hz = 500_000
            spi.mode = 0
            for stage in ('HANDS OFF: leave the little screen untouched',
                          'PRESS: press and HOLD near the CENTER of the little screen',
                          'RELEASE: lift your finger and leave the screen untouched'):
                report('\n'+stage+' for 8 seconds')
                for second in range(8):
                    z1,z2,xs,ys = read_burst(spi)
                    x,y = median(xs),median(ys)
                    pressure = z1+4095-z2
                    gate = 0 < z1 < z2 < 4095 and pressure >= 300
                    report(f'{second+1}/8  X={x:4d} Y={y:4d} Z1={z1:4d} Z2={z2:4d} pressure={pressure:4d} pressure_gate={gate}')
                    time.sleep(1)
            report(f'\nDone. Send a photo showing all three sections. Log saved: {path}')
        finally:
            spi.close()


if __name__=='__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'Touch diagnostic stopped: {exc}',file=sys.stderr)
        sys.exit(1)
