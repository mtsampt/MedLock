import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('display_bridge',Path(__file__).parents[1]/'scripts/mirror_pi_display.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)

SOURCE='''
WIDTH=320
HEIGHT=240
DC_GPIO=22
BL_GPIO=18
spi.open(0,0)
def command(value,data=None):
    dc.append((value,data))
def init_lcd():
    command(1)
def display_image(image):
    command(44,[image])
raise RuntimeError('Top-level startup and loop must not run')
'''


def test_load_only_the_three_display_functions():
    code,constants=bridge.extract_functions(SOURCE)
    ns={'dc':[],**constants}
    exec(code,ns)
    ns['init_lcd']();ns['display_image']('frame')
    assert ns['dc']==[(1,None),(44,['frame'])]


def test_reject_other_wiring_or_incomplete_driver():
    for source in [SOURCE.replace('DC_GPIO=22','DC_GPIO=23'),SOURCE.replace('spi.open(0,0)','spi.open(0,1)'),SOURCE.replace('def init_lcd():','def other_init():')]:
        with pytest.raises(ValueError):bridge.extract_functions(source)


def test_touch_forwarding_uses_displayed_revision_and_hit_regions(monkeypatch):
    import json
    import io
    calls=[]
    def open_request(request,timeout):
        calls.append(json.loads(request.data))
        return io.BytesIO(b'{}')
    monkeypatch.setattr(bridge,'urlopen',open_request)
    state={'session_id':'test','revision':7,'buttons':[{'action':'capture','x':164,'y':180,'width':144,'height':48}]}
    assert not bridge.forward_tap('http://localhost/api/touch',state,10,10)
    assert bridge.forward_tap('http://localhost/api/touch',state,200,200)
    assert calls==[{'action':'capture','session_id':'test','revision':7}]
    with pytest.raises(ValueError):
        bridge.forward_tap('http://localhost/api/touch',{'buttons':[]},200,200)


def test_stale_touch_response_does_not_stop_bridge(monkeypatch):
    from urllib.error import HTTPError
    def stale(request,timeout):
        raise HTTPError(request.full_url,409,'stale',{},None)
    monkeypatch.setattr(bridge,'urlopen',stale)
    state={'session_id':'test','revision':1,'buttons':[{'action':'seat','x':12,'y':180,'width':144,'height':48}]}
    assert bridge.forward_tap('http://localhost/api/touch',state,20,200)


def test_touch_hold_triggers_once_per_press():
    from types import SimpleNamespace as S
    from medlock_device.display_hardware import EvdevTouch
    touch=EvdevTouch.__new__(EvdevTouch)
    touch.codes=S(EV_ABS=3,ABS_X=0,ABS_Y=1,EV_KEY=1,BTN_TOUCH=330,EV_SYN=0,SYN_DROPPED=3,SYN_REPORT=0)
    touch.xinfo=touch.yinfo=S(min=0,max=4095)
    touch.swap=touch.invert_x=touch.invert_y=False
    touch.x=touch.y=None;touch.pressed=touch.sent=False
    events=[S(type=3,code=0,value=2048),S(type=3,code=1,value=2048),S(type=1,code=330,value=1),S(type=0,code=0,value=0)]
    touch.device=S(read=lambda:events)
    assert touch.read_taps()==[(160,120)]
    assert touch.read_taps()==[]
    events=[S(type=1,code=330,value=0),S(type=0,code=0,value=0)]
    assert touch.read_taps()==[]
    events=[S(type=1,code=330,value=1),S(type=0,code=0,value=0)]
    assert touch.read_taps()==[(160,120)]


def test_knob_input_during_slow_lcd_write_is_not_lost():
    from PIL import Image
    from medlock_device.knob_navigation import KnobNavigation
    nav=KnobNavigation()
    state={'revision':7,'buttons':[
        {'action':'seat','x':12,'y':180,'width':144,'height':48},
        {'action':'capture','x':164,'y':180,'width':144,'height':48}]}
    frame=Image.new('RGB',(320,240),'white')
    previous=bridge.paint_frame(frame,state,nav,lambda image:None,None)
    nav.emit('next');nav.read()
    # A press arrives from the GPIO thread while SPI sends the focus redraw.
    previous=bridge.paint_frame(frame,state,nav,lambda image:nav.emit('press'),previous)
    visible,button=nav.read()
    assert visible['revision']==7 and button['action']=='capture'


def test_knob_redraw_cannot_retarget_old_press_to_new_screen():
    from PIL import Image
    from medlock_device.knob_navigation import KnobNavigation
    nav=KnobNavigation()
    old={'revision':1,'buttons':[{'action':'capture','x':12,'y':180,'width':296,'height':48}]}
    new={'revision':2,'buttons':[{'action':'retry','x':12,'y':180,'width':296,'height':48}]}
    frame=Image.new('RGB',(320,240),'white')
    previous=bridge.paint_frame(frame,old,nav,lambda image:None,None)
    # Event occurring before the new physical frame is committed belongs to old.
    frame.putpixel((0,0),(0,0,0))
    bridge.paint_frame(frame,new,nav,lambda image:nav.emit('press'),previous)
    assert nav.read() is None
    nav.emit('press')
    assert nav.read()[1]['action']=='retry'


def test_knob_is_default_and_explicit_input_modes_do_not_claim_it():
    assert bridge.parse_args([]).knob
    assert bridge.parse_args(['--knob']).knob
    assert not bridge.parse_args(['--no-knob']).knob
    assert not bridge.parse_args(['--spi-touch']).knob
    assert not bridge.parse_args(['--touch-device','/dev/input/event4']).knob
    with pytest.raises(SystemExit):bridge.parse_args(['--knob','--spi-touch'])
