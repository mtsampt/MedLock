import queue
import threading
import time
from types import SimpleNamespace

from medlock_device.encoder import EncoderInput
from test_integration import flow, act


def test_shared_focus_then_press_progresses_controller(flow):
    flow.encoder_event('press')
    assert flow.snapshot()['screen']=='start' and flow.snapshot()['focus_action']=='begin'
    flow.encoder_event('press')
    assert flow.snapshot()['screen']=='supplies'
    flow.encoder_event('press');flow.encoder_event('press')
    assert flow.snapshot()['confirmed']==['diluent']
    flow.encoder_event('next')
    assert flow.snapshot()['focus_action']=='help'
    flow.encoder_event('press')
    assert flow.snapshot()['help_open']


def test_gpio_callbacks_queue_only_and_worker_dispatches(flow):
    from gpiozero.pins.mock import MockFactory
    encoder=EncoderInput(5,6,13,pin_factory=MockFactory())
    stop=threading.Event()
    try:
        encoder.encoder.when_rotated_clockwise()
        assert encoder.events.get_nowait()==('next',None)
        encoder.encoder.when_rotated_counter_clockwise()
        assert encoder.events.get_nowait()==('previous',None)
        encoder.switch.when_pressed()
        assert flow.snapshot()['screen']=='start'
        worker=threading.Thread(target=encoder.run,args=(flow,stop))
        worker.start()
        deadline=time.monotonic()+2
        while flow.snapshot()['focus_action'] is None and time.monotonic()<deadline:time.sleep(.01)
        assert flow.snapshot()['focus_action']=='begin'
        stop.set();worker.join(2)
        assert not worker.is_alive()
    finally:
        stop.set();encoder.close()


def test_old_queued_press_cannot_activate_a_different_screen(flow):
    state=flow.snapshot()
    token=(state['session_id'],state['revision'])
    flow.encoder_event('press',token)
    from medlock_device.state_machine import FlowError
    import pytest
    with pytest.raises(FlowError):flow.encoder_event('press',token)
    assert flow.snapshot()['screen']=='start'
