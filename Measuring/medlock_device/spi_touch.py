"""IRQ-free XPT2046 polling for the Gerber-confirmed REV B SPI0.1 wiring.

Uses 12-bit differential X/Y/Z conversions; pressure proxy follows the
controller convention Z1 + 4095 - Z2. No GPIO interrupt or kernel overlay.
"""
import json
import math
from pathlib import Path
from statistics import median
import time


def read_burst(spi):
    """Keep CS low and the ADC powered throughout one pipelined sample.

    Command/receive sequencing follows the XPT2046 serial protocol used by
    PJRC's controller driver. First coordinate conversion is discarded;
    the final command powers down after the last coordinate conversion.
    Reference: github.com/PaulStoffregen/XPT2046_Touchscreen
    """
    data = spi.xfer2([0xB1,0,0xC1,0,0x91,0,0x91,0,0xD1,0,
                      0x91,0,0xD1,0,0x91,0,0xD0,0,0])
    def value(offset):
        return ((data[offset] << 8) | data[offset+1]) >> 3 & 4095
    return value(1),value(3),[value(i) for i in (7,11,15)],[value(i) for i in (9,13,17)]


class SpiTouch:
    def __init__(self, calibration_path):
        import spidev
        self.path = Path(calibration_path)
        self.matrix = None
        if self.path.exists():
            values = json.loads(self.path.read_text())['matrix']
            if len(values) != 6 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
                raise ValueError('Invalid touch calibration. Run with --calibrate-touch.')
            self.matrix = values
        self.spi = spidev.SpiDev()
        try:
            self.spi.open(0, 1)  # TOUCH_CS = BCM7 / physical pin26, REV B Gerbers
            self.spi.max_speed_hz = 500_000
            self.spi.mode = 0
        except Exception:
            self.spi.close()
            raise
        self.sent = False
        self.released = 0
        self.candidate = None

    def sample(self):
        z1,z2,xs,ys = read_burst(self.spi)
        if not (0 < z1 < z2 < 4095) or z1 + 4095 - z2 < 300:
            return None
        if max(xs)-min(xs) > 120 or max(ys)-min(ys) > 120:
            return None
        return median(xs), median(ys)

    def read_taps(self):
        point = self.sample()
        if point is None:
            self.released += 1
            self.candidate = None
            if self.released >= 3:
                self.sent = False
            return []
        self.released = 0
        if self.sent:
            return []
        previous, self.candidate = self.candidate, point
        if previous is None or max(abs(a-b) for a,b in zip(previous, point)) > 100:
            return []
        self.sent = True
        if self.matrix is None:
            raise ValueError('Touch must be calibrated first.')
        x, y = transform(self.matrix, point)
        if not (-10 <= x <= 329 and -10 <= y <= 249):
            return []
        return [(round(max(0, min(319, x))), round(max(0, min(239, y))))]

    def close(self):
        self.spi.close()


def transform(matrix, point):
    a,b,c,d,e,f = matrix
    x,y = point
    return a*x+b*y+c, d*x+e*y+f


def fit_calibration(raw, targets):
    """Fit three points; independently check the fourth before saving."""
    (x0,y0),(x1,y1),(x2,y2) = raw[:3]
    dx1,dy1,dx2,dy2 = x1-x0,y1-y0,x2-x0,y2-y0
    det = dx1*dy2-dx2*dy1
    if abs(det) < 100_000:
        raise ValueError('Calibration points too close. Retry the four targets.')
    matrix = []
    for axis in (0,1):
        q0,q1,q2 = [p[axis] for p in targets[:3]]
        a = ((q1-q0)*dy2-(q2-q0)*dy1)/det
        b = (dx1*(q2-q0)-dx2*(q1-q0))/det
        matrix.extend((a,b,q0-a*x0-b*y0))
    check = transform(matrix,raw[3])
    if math.dist(check,targets[3]) > 18:
        raise ValueError('Calibration check missed by more than 18 pixels. Retry the targets.')
    return matrix


def calibrate(touch, show):
    from PIL import Image, ImageDraw
    targets = [(30,30),(289,30),(289,209),(30,209)]
    raw = []
    for index,(x,y) in enumerate(targets):
        image = Image.new('RGB',(320,240),'white')
        draw = ImageDraw.Draw(image)
        draw.text((85,95),f'Touch setup {index+1}/4',fill='black')
        draw.text((65,115),'Press + briefly, then lift',fill='black')
        draw.ellipse((x-12,y-12,x+12,y+12),outline='blue',width=2)
        draw.line((x-18,y,x+18,y),fill='blue',width=2)
        draw.line((x,y-18,x,y+18),fill='blue',width=2)
        show(image)
        deadline = time.monotonic()+120
        # Require release before each target, then stable readings and release.
        released = 0
        samples = []
        armed = False
        while time.monotonic() < deadline:
            point = touch.sample()
            if point is None:
                released += 1
                if released >= 3:
                    if armed and len(samples) >= 4:
                        raw.append(tuple(median(p[i] for p in samples) for i in (0,1)))
                        break
                    armed = True
                    samples = []
            else:
                released = 0
                if armed:
                    if samples and max(abs(a-b) for a,b in zip(samples[-1],point)) > 100:
                        samples = []
                    samples.append(point)
            time.sleep(.03)
        else:
            raise RuntimeError('Touch setup timed out. No usable press/release detected; send terminal output.')
    matrix = fit_calibration(raw, targets)
    touch.path.parent.mkdir(parents=True,exist_ok=True)
    touch.path.write_text(json.dumps({'matrix':matrix,'raw':raw,'targets':targets},indent=2)+'\n')
    touch.matrix = matrix
    touch.sent = False
    print(f'Touch calibration saved to {touch.path}',flush=True)
