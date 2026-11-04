import io
import threading
import time
from types import SimpleNamespace

from PIL import Image

from medlock_device.display_hardware import map_touch
from medlock_device.touchscreen import TouchUI, buttons, render
from medlock_device.web import create_app


class FakeStation:
    seat=None
    camera=SimpleNamespace(mode='photo replay — simulated hardware')
    engine=SimpleNamespace(metadata={'version':'test'})
    preview=None
    result={}
    calls=0
    def check(self,seated):
        self.calls+=1
        time.sleep(.02)
        return {'state':'no_air_detected' if seated else 'unable',
                'message':'No visible air detected' if seated else 'Syringe is not seated.',
                'inference_ms':12,'elapsed_ms':200},200


def wait_done(ui):
    deadline=time.monotonic()+2
    while ui.snapshot()['screen']=='checking' and time.monotonic()<deadline:
        time.sleep(.01)
    assert ui.snapshot()['screen']=='result'


def test_shared_ui_capture_details_retry_and_no_double_capture():
    s=FakeStation();ui=TouchUI(s)
    assert ui.action('seat')
    assert ui.action('capture')
    assert not ui.action('capture') and not ui.action('details')
    assert ui.snapshot()['buttons']==[]
    wait_done(ui)
    assert s.calls==1 and ui.snapshot()['result']['state']=='no_air_detected'
    assert ui.action('details') and ui.snapshot()['screen']=='details'
    assert ui.action('back') and ui.action('retry')
    assert not ui.snapshot()['seated'] and not ui.snapshot()['result']
    assert ui.action('capture');wait_done(ui)
    assert ui.snapshot()['result']['state']=='unable'


def test_gpio_does_not_offer_a_simulated_seat_button():
    s=FakeStation();s.seat=object();ui=TouchUI(s)
    assert not ui.action('seat')
    assert [b['action'] for b in ui.snapshot()['buttons']]==['help','capture']


def test_all_frames_and_touch_regions_fit_exact_display():
    for screen in ['ready','checking','result','details','help']:
        for status in ['air_detected','no_air_detected','unable']:
            for gpio in [True,False]:
                state={'screen':screen,'replay':True,'gpio':gpio,'seated':False,
                       'result':{'state':status,'message':'A very long failure message '*50},
                       'buttons':buttons(screen,False,gpio)}
                assert render(state,Image.new('RGB',(224,224))).size==(320,240)
                for b in state['buttons']:
                    assert b['width']>=44 and b['height']>=44
                    assert 0<=b['x'] and b['x']+b['width']<=320
                    assert 0<=b['y'] and b['y']+b['height']<=240


def test_frame_api_and_origin_guard():
    client=create_app(FakeStation()).test_client()
    assert b'touch.js' in client.get('/').data
    assert b'app.js' in client.get('/desktop').data
    frame=client.get('/api/touch/frame')
    assert Image.open(io.BytesIO(frame.data)).size==(320,240)
    assert client.post('/api/touch',json={'action':'details'}).status_code==409
    assert client.post('/api/touch',json={'action':'seat'}).status_code==200
    assert client.post('/api/touch',json={'action':'capture'},headers={'Origin':'https://example.com'}).status_code==403


def test_touch_calibration_corners_rotation_and_clamping():
    assert map_touch(200,300,200,3800,300,3900)==(0,0)
    assert map_touch(3800,3900,200,3800,300,3900)==(319,239)
    assert map_touch(200,3900,200,3800,300,3900,swap=True)==(319,0)
    assert map_touch(200,300,200,3800,300,3900,invert_x=True,invert_y=True)==(319,239)
    assert map_touch(-100,9000,200,3800,300,3900)==(0,239)


def test_help_returns_to_the_same_screen_without_clearing_result():
    ui=TouchUI(FakeStation())
    assert ui.action('help') and ui.snapshot()['screen']=='help'
    assert ui.action('close_help') and ui.snapshot()['screen']=='ready'
    ui.action('seat');ui.action('capture');wait_done(ui)
    result=ui.snapshot()['result']
    ui.action('help');ui.action('close_help')
    assert ui.snapshot()['screen']=='result' and ui.snapshot()['result']==result
