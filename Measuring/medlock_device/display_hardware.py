"""Optional Pi-only ILI9341 output and Linux resistive-touch input adapters.

Requires SPI wiring and an XPT2046/ADS7846 kernel input device configured by
hardware integration. This module imports hardware libraries only when used.
"""
import json
import time
from .touchscreen import TouchUI


def map_touch(x, y, xmin, xmax, ymin, ymax, swap=False, invert_x=False, invert_y=False):
    if xmax <= xmin or ymax <= ymin:
        raise ValueError('Touch input calibration ranges are invalid.')
    x=(x-xmin)/(xmax-xmin)
    y=(y-ymin)/(ymax-ymin)
    if swap:x,y=y,x
    if invert_x:x=1-x
    if invert_y:y=1-y
    return round(max(0,min(1,x))*319),round(max(0,min(1,y))*239)


class ILI9341Display:
    def __init__(self, cs, dc, reset, rotation=90):
        import board
        import digitalio
        from adafruit_rgb_display import ili9341
        self.pins=[]
        self.spi=None
        try:
            for number in (cs,dc,reset):
                self.pins.append(digitalio.DigitalInOut(getattr(board,f'D{number}')))
            self.spi=board.SPI()
            self.display=ili9341.ILI9341(self.spi,cs=self.pins[0],dc=self.pins[1],rst=self.pins[2],
                                        rotation=rotation,baudrate=16_000_000)
        except Exception:
            self.close()
            raise

    def show(self, image):
        if image.size != (320,240):
            raise ValueError('Display frames must be exactly 320 x 240.')
        self.display.image(image)

    def close(self):
        for pin in self.pins:pin.deinit()
        if self.spi:self.spi.deinit()


class EvdevTouch:
    """Single-tap-on-press input from an already configured ADS7846 device."""
    def __init__(self, path, swap=False, invert_x=False, invert_y=False, exclusive=False):
        import evdev
        self.codes=evdev.ecodes
        self.device=evdev.InputDevice(str(path))
        self.xinfo=self.device.absinfo(self.codes.ABS_X)
        self.yinfo=self.device.absinfo(self.codes.ABS_Y)
        if self.xinfo is None or self.yinfo is None:
            self.device.close()
            raise ValueError('Select the touchscreen event device with ABS_X and ABS_Y axes.')
        if self.xinfo.max<=self.xinfo.min or self.yinfo.max<=self.yinfo.min:
            self.device.close()
            raise ValueError('Touch input axes have invalid calibration ranges.')
        if exclusive:
            try:self.device.grab()
            except Exception:
                self.device.close()
                raise
        self.swap,self.invert_x,self.invert_y=swap,invert_x,invert_y
        self.x=self.y=None
        self.pressed=self.sent=False

    def read_taps(self):
        try:events=list(self.device.read())
        except BlockingIOError:return []
        taps=[];c=self.codes
        for event in events:
            if event.type==c.EV_ABS:
                if event.code==c.ABS_X:self.x=event.value
                elif event.code==c.ABS_Y:self.y=event.value
            elif event.type==c.EV_KEY and event.code==c.BTN_TOUCH:
                self.pressed=bool(event.value)
                if not self.pressed:self.sent=False
            elif event.type==c.EV_SYN:
                if event.code==c.SYN_DROPPED:
                    self.x=self.y=None;self.pressed=False;self.sent=False
                elif event.code==c.SYN_REPORT and self.pressed and not self.sent and self.x is not None and self.y is not None:
                    taps.append(map_touch(self.x,self.y,self.xinfo.min,self.xinfo.max,self.yinfo.min,self.yinfo.max,
                                          self.swap,self.invert_x,self.invert_y))
                    self.sent=True
        return taps

    def close(self):self.device.close()


def run_native(station,args):
    ui=TouchUI(station)
    display=ILI9341Display(args.display_cs,args.display_dc,args.display_reset,args.display_rotation)
    touch=None
    try:
        touch=EvdevTouch(args.touch_device,args.touch_swap,args.touch_invert_x,args.touch_invert_y)
        previous=None
        while True:
            for x,y in touch.read_taps():
                for b in ui.snapshot()['buttons']:
                    if b['x']<=x<b['x']+b['width'] and b['y']<=y<b['y']+b['height']:
                        ui.action(b['action']);break
            signature=json.dumps(ui.snapshot(),sort_keys=True)
            if signature!=previous:
                display.show(ui.render())
                previous=signature
            time.sleep(.05)
    finally:
        if touch:touch.close()
        display.close()
