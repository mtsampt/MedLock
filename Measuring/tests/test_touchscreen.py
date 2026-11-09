import pytest
from PIL import Image

from medlock_device.display_hardware import map_touch
from medlock_device.touchscreen import TouchUI, render
from test_integration import flow, act, ready, checked


def test_native_uses_same_session_and_disallows_double_capture(flow):
    ui = TouchUI(flow)
    assert ui.action('begin')
    assert not ui.action('capture')
    act(flow, 'reset'); ready(flow)
    assert ui.action('seat') and ui.action('capture')
    assert not ui.action('capture')
    flow.worker.join(3)
    assert ui.snapshot()['result']['verdict'] == 'unable'
    assert ui.action('help') and ui.action('close_help')
    assert ui.action('retry') and not ui.snapshot()['seated']


def test_all_guided_frames_and_buttons_fit_display(flow):
    ui = TouchUI(flow)
    states = [ui.snapshot()]
    act(flow, 'begin')
    for _ in flow.protocol['supplies']:
        states.append(ui.snapshot())
        act(flow, 'missing'); states.append(ui.snapshot()); act(flow, 'confirm')
    for _ in flow.protocol['prep_steps']:
        states.append(ui.snapshot()); act(flow, 'next')
    states.append(ui.snapshot())
    act(flow, 'seat'); checked(flow); states.append(ui.snapshot())
    act(flow, 'help'); states.append(ui.snapshot())
    for state in states:
        assert render(state).size == (320, 240)
        for button in state['buttons']:
            assert button['width'] >= 44 and button['height'] >= 44
            assert 0 <= button['x'] <= 320 - button['width']
            assert 0 <= button['y'] <= 240 - button['height']


def test_stale_touch_does_not_act_on_changed_screen(flow):
    ui = TouchUI(flow)
    before = ui.snapshot()
    act(flow, 'begin')
    assert not ui.action('begin', before)


def test_touch_calibration_corners_rotation_and_clamping():
    assert map_touch(200,300,200,3800,300,3900)==(0,0)
    assert map_touch(3800,3900,200,3800,300,3900)==(319,239)
    assert map_touch(200,3900,200,3800,300,3900,swap=True)==(319,0)
    assert map_touch(200,300,200,3800,300,3900,invert_x=True,invert_y=True)==(319,239)
    assert map_touch(-100,9000,200,3800,300,3900)==(0,239)
    with pytest.raises(ValueError): map_touch(0,0,1,1,1,1)
