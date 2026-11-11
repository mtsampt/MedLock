"""Compare a published driver with MedLock's touch reader on REV B wiring."""
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from third_party.xpt2046_asukiaaa.driver import XPT2046


def main():
    import spidev
    path = ROOT/'outputs/independent-touch.txt'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w') as log:
        def report(line):
            print(line,flush=True)
            log.write(line+'\n')
            log.flush()
        spi = spidev.SpiDev()
        try:
            spi.open(0,1)
            touch = XPT2046(spi,None)
            report('Independent XPT2046-asukiaaa driver 1.0.0 / SPI0.1 / 1 MHz')
            report('Stop the MedLock bridge first. Watch THIS terminal, not the little LCD.')
            report('Counts use the published library decoding; no MedLock pressure filter.')
            for stage in ('HANDS OFF: leave the little screen untouched',
                          'PRESS: hold the CENTER of the little screen',
                          'MOVE: keep pressing and slowly slide across the screen',
                          'RELEASE: lift your finger completely'):
                report('\n'+stage+' for 6 seconds')
                for second in range(6):
                    values = []
                    for _ in range(10):
                        values.append(tuple(touch._send_command(c) for c in
                                            (touch.GET_X,touch.GET_Y,touch.GET_Z1,touch.GET_Z2)))
                        time.sleep(.1)
                    # Report ranges to expose noise; don't call these presses.
                    ranges = ' '.join(f'{name}={min(v[i] for v in values)}..{max(v[i] for v in values)}'
                                      for i,name in enumerate(('X','Y','Z1','Z2')))
                    report(f'{second+1}/6  {ranges}')
            report(f'\nDone. Send terminal photos from all four sections. Log: {path}')
        finally:
            spi.close()


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except Exception as exc:
        print(f'Independent touch test stopped: {exc}',file=sys.stderr)
        sys.exit(1)
