import json
from types import SimpleNamespace

import pytest

from medlock_device.spi_touch import SpiTouch, fit_calibration, transform, read_burst


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
        reply = [0]*19
        for offset,value in [(1,800),(3,3000),(5,4095),(7,2000),(9,1000),
                             (11,2000),(13,1000),(15,2000),(17,1000)]:
            reply[offset] = value>>5
            reply[offset+1] = (value<<3)&255
        return reply
    device = SimpleNamespace(open=lambda *a:None,close=lambda:None,xfer2=transfer)
    monkeypatch.setitem(sys.modules,'spidev',SimpleNamespace(SpiDev=lambda:device))
    touch = SpiTouch(tmp_path/'calibration.json')
    assert touch.sample() == (2000,1000)
    assert device.mode == 0 and device.max_speed_hz == 500_000
    assert len(calls)==1 and len(calls[0])==19
    assert calls[0][::2] == [0xB1,0xC1,0x91,0x91,0xD1,0x91,0xD1,0x91,0xD0,0]
    for reply in ([0]*19,[255]*19):
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


def test_burst_preserves_axis_order_and_rejects_unstable_coordinates():
    reply = [0]*19
    for offset,value in [(1,800),(3,3000),(5,0),(7,2000),(9,1000),
                         (11,2010),(13,1010),(15,2200),(17,1020)]:
        reply[offset],reply[offset+1] = value>>5,(value<<3)&255
    touch = SpiTouch.__new__(SpiTouch)
    touch.spi = SimpleNamespace(xfer2=lambda tx:reply)
    assert read_burst(touch.spi) == (800,3000,[2000,2010,2200],[1000,1010,1020])
    assert touch.sample() is None
