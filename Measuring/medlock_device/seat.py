"""Rev0 optical seat input: external pull-up, HIGH means seated (report §6.2)."""
import threading
import time


class SeatSensor:
    def __init__(self, pin, active='high', pull='external', pin_factory=None):
        from gpiozero import Button
        if active not in {'high', 'low'} or pull not in {'external', 'up', 'down'}:
            raise ValueError('Invalid seat polarity/pull configuration.')
        if (pull == 'up' and active != 'low') or (pull == 'down' and active != 'high'):
            raise ValueError('Internal seat pull must oppose its active level.')
        kwargs = dict(pull_up=None, active_state=active == 'high') if pull == 'external' else dict(pull_up=pull == 'up')
        self.lock = threading.RLock()
        self.device = Button(pin, bounce_time=.05, pin_factory=pin_factory, **kwargs)
        self.state = bool(self.device.is_pressed)
        self._generation = 0
        self._seated_at = time.monotonic() if self.state else None
        self.device.when_pressed = lambda: self._update(True)
        self.device.when_released = lambda: self._update(False)

    def _update(self, seated):
        with self.lock:
            if self.state != seated:
                self.state = seated
                self._generation += 1
                self._seated_at = time.monotonic() if seated else None

    @property
    def is_pressed(self):
        self._update(bool(self.device.is_pressed))
        return self.state

    @property
    def generation(self):
        self.is_pressed
        return self._generation

    @property
    def seated_at(self):
        self.is_pressed
        return self._seated_at

    def close(self):
        self.device.when_pressed = self.device.when_released = None
        self.device.close()
