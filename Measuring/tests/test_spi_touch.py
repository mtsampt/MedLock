import json
from types import SimpleNamespace

import pytest

from medlock_device.spi_touch import SpiTouch, fit_calibration, transform


def test_rotated_inverted_calibration_and_bad_fourth_point():
    targets = [(30,30),(289,30),(289,209),(30,209)]
    raw = [(3500,400),(3500,3600),(500,3600),(500,400)]
    matrix = fit_calibration(raw, targets)
    for point,target in zip(raw,targets):
        assert transform(matrix,point) == pytest.approx(target)
    with pytest.raises(ValueError, match='check missed'):
        fit_calibration(raw[:3]+[(1500,1500)],targets)
    with pytest.raises(ValueError, match='too close'):
        fit_calibration([(1,1)]*4,targets)


def test_spi_transactions_and_disconnected_lines(monkeypatch,tmp_path):
    import sys
    calls = []
    def transfer(data):
        calls.append(data)
        value = {0xB0:800,0xC0:3000,0xD0:2000,0x90:1000}[data[0]]
        return [0,(value<<3)>>8,(value<<3)&255]
    device = SimpleNamespace(open=lambda *a:None,close=lambda:None,xfer2=transfer)
    monkeypatch.setitem(sys.modules,'spidev',SimpleNamespace(SpiDev=lambda:device))
    touch = SpiTouch(tmp_path/'calibration.json')
    assert touch.sample() == (2000,1000)
    assert device.mode == 0 and device.max_speed_hz == 500_000
    assert all(len(call)==3 and call[1:]==[0,0] for call in calls)
    for reply in ([0,0,0],[255,255,255]):
        device.xfer2 = lambda data:reply
        assert touch.sample() is None


def test_hold_and_short_noise_gap_do_not_repeat_action():
    touch = SpiTouch.__new__(SpiTouch)
    touch.matrix = [319/4095,0,0,0,239/4095,0]
    touch.sent = False
    touch.released = 0
    touch.candidate = None
    points = iter([(2048,2048)]*4+[None]+[(2048,2048)]*2+[None]*3+[(2048,2048)]*2)
    touch.sample = lambda:next(points)
    actions = [touch.read_taps() for _ in range(12)]
    assert [i for i,v in enumerate(actions) if v] == [1,11]
    assert actions[1] == [(160,120)]
