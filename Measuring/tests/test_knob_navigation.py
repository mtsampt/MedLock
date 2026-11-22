from types import SimpleNamespace
import sys

import pytest
from PIL import Image

from medlock_device.knob_navigation import KnobNavigation, load_knob


def state(revision=1):
    return {'revision':revision,'buttons':[
        {'action':a,'x':x,'y':180,'width':80,'height':48}
        for a,x in [('help',0),('seat',90),('capture',180)]]}


def test_rotate_select_and_visible_focus():
    nav=KnobNavigation();nav.sync(state())
    assert nav.selected=='seat'
    nav.emit('next');assert nav.read() is None
    assert nav.selected=='capture'
    frame=Image.new('RGB',(320,240),'white')
    focused=nav.draw(frame)
    assert focused.getpixel((220,186))!=(255,255,255)
    assert frame.getpixel((220,186))==(255,255,255)
    nav.emit('press')
    visible,button=nav.read()
    assert visible['revision']==1 and button['action']=='capture'
    nav.emit('next');nav.read();assert nav.selected=='help'
    nav.emit('prev');nav.read();assert nav.selected=='capture'


def test_stale_events_and_checking_screen_cannot_trigger_buttons():
    nav=KnobNavigation();nav.sync(state())
    nav.emit('press');nav.sync(state(revision=2))
    assert nav.read() is None
    nav.sync({'revision':3,'buttons':[]});nav.emit('press')
    assert nav.read() is None
    nav.sync(None);nav.emit('press');assert nav.read() is None


def test_shared_knob_callbacks_cleanup_and_no_evdev_required(monkeypatch):
    devices=[]
    class Device:
        def __init__(self,*args,**kwargs):
            self.args=args;self.options=kwargs;self.closed=False;devices.append(self)
        def close(self):self.closed=True
    monkeypatch.setitem(sys.modules,'gpiozero',SimpleNamespace(Button=Device,RotaryEncoder=Device))
    nav=KnobNavigation();nav.attach(reverse=True,button_active_high=True)
    nav.sync(state())
    encoder,button=devices
    assert encoder.args==(5,6) and button.args==(13,)
    assert button.options['pull_up'] is False
    encoder.when_rotated_clockwise();nav.read();assert nav.selected=='help'
    encoder.when_rotated_counter_clockwise();nav.read();assert nav.selected=='seat'
    button.when_pressed();assert nav.read()[1]['action']=='seat'
    nav.close();assert all(d.closed for d in devices)


def test_shared_knob_releases_encoder_when_button_fails(monkeypatch):
    encoder=SimpleNamespace(close=lambda:closed.append(True))
    closed=[]
    def fail(*args,**kwargs):raise RuntimeError('busy')
    monkeypatch.setitem(sys.modules,'gpiozero',SimpleNamespace(RotaryEncoder=lambda *a,**k:encoder,Button=fail))
    with pytest.raises(RuntimeError,match='busy'):load_knob().attach_controls(lambda a:None)
    assert closed==[True]
    with pytest.raises(ValueError,match='conflicts'):KnobNavigation().attach(a=22)


def test_real_gpiozero_decoder_with_simulated_electrical_edges():
    gpiozero=pytest.importorskip('gpiozero')
    from gpiozero.pins.mock import MockFactory
    previous=gpiozero.Device.pin_factory
    factory=MockFactory()
    gpiozero.Device.pin_factory=factory
    nav=KnobNavigation()
    try:
        nav.attach()
        nav.sync(state())
        a,b,button=(factory.pin(pin) for pin in (5,6,13))
        # Ground common, pulled-up contacts: complete Gray-code quadrature.
        a.drive_low();b.drive_low();a.drive_high();b.drive_high()
        nav.read()
        first=nav.selected
        assert first!='seat'
        b.drive_low();a.drive_low();b.drive_high();a.drive_high()
        nav.read()
        assert nav.selected=='seat'
        button.drive_low()
        assert nav.read()[1]['action']=='seat'
        # Holding down must not generate repeat presses.
        assert nav.read() is None
        button.drive_high()
        status=nav.status()
        assert status['levels']=={'A':1,'B':1,'SW':1}
        assert status['events']==3
    finally:
        nav.close()
        gpiozero.Device.pin_factory=previous
        factory.close()
