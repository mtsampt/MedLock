import time
from types import SimpleNamespace
import pytest

from medlock_device.seat import SeatSensor
from test_integration import flow, ready, act, checked


def test_rev0_high_means_seated_with_external_pull():
    from gpiozero.pins.mock import MockFactory
    seat=SeatSensor(17,pin_factory=MockFactory())
    try:
        seat.device.pin.drive_low()
        assert not seat.is_pressed
        seat.device.pin.drive_high()
        assert seat.is_pressed and seat.seated_at is not None
        generation=seat.generation
        time.sleep(.06)
        seat.device.pin.drive_low()
        assert not seat.is_pressed and seat.seated_at is None
        time.sleep(.06)
        seat.device.pin.drive_high()
        assert seat.is_pressed and seat.generation > generation
    finally:seat.close()


def test_explicit_legacy_low_polarity():
    from gpiozero.pins.mock import MockFactory
    seat=SeatSensor(17,active='low',pull='up',pin_factory=MockFactory())
    try:
        seat.device.pin.drive_high();assert not seat.is_pressed
        seat.device.pin.drive_low();assert seat.is_pressed
    finally:seat.close()


def test_lift_then_reseat_invalidates_old_result(flow):
    seat=SimpleNamespace(is_pressed=True,generation=0,seated_at=time.monotonic())
    flow.station.seat=seat
    ready(flow)
    state=checked(flow)
    assert state['result']['seat_generation']==0 and state['result']['seat_to_result_ms'] is not None
    seat.generation=2  # a low/high transition occurred between controller polls
    assert flow.snapshot()['screen']=='check' and flow.snapshot()['result'] is None


def test_movement_during_capture_detected_even_if_reseated(flow):
    seat=SimpleNamespace(is_pressed=True,generation=0,seated_at=time.monotonic())
    flow.station.seat=seat
    original=flow.station.camera.capture
    def capture():
        seat.generation+=2
        return original()
    flow.station.camera.capture=capture
    result,_=flow.station.check()
    assert result['state']=='unable' and 'moved' in result['message']
