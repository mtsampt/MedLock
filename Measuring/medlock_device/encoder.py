"""Optional quadrature encoder/pushbutton; dispatches to the shared Session."""
import logging
import queue


class EncoderInput:
    def __init__(self, a, b, switch, pin_factory=None, session=None):
        from gpiozero import Button, RotaryEncoder
        self.events = queue.Queue(maxsize=32)
        self.session = session
        self.encoder = RotaryEncoder(a, b, max_steps=0, pin_factory=pin_factory)
        try:
            self.switch = Button(switch, pull_up=True, bounce_time=.05, pin_factory=pin_factory)
        except Exception:
            self.encoder.close()
            raise
        self.encoder.when_rotated_clockwise = lambda: self._queue('next')
        self.encoder.when_rotated_counter_clockwise = lambda: self._queue('previous')
        self.switch.when_pressed = lambda: self._queue('press')

    def _queue(self, event):
        try:
            state = self.session.snapshot() if event == 'press' and self.session is not None else None
            token = (state['session_id'], state['revision']) if state is not None else None
            self.events.put_nowait((event, token))
        except queue.Full:
            pass  # discard excess rotation; never replay a backlog of selections

    def run(self, session, stop):
        from .state_machine import FlowError
        while not stop.is_set():
            try:
                event, token = self.events.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                session.encoder_event(event, token)
            except FlowError as exc:
                logging.warning('Encoder action rejected: %s', exc)

    def close(self):
        try:
            self.switch.close()
        finally:
            self.encoder.close()
