"""Thread-safe, authoritative station flow shared by browser and native display."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import threading
import time
import uuid


class FlowError(ValueError):
    def __init__(self, message, code=409):
        super().__init__(message)
        self.code = code


def load_protocol(path=None):
    data = json.loads(Path(path or Path(__file__).with_name('protocol.json')).read_text())
    if data.get('prototype') is not True:
        raise ValueError('Only bench prototype protocols are supported.')
    for key in ('supplies', 'prep_steps'):
        items = data.get(key)
        if not isinstance(items, list) or not items or len(items) > 20:
            raise ValueError(f'Protocol needs 1–20 {key}.')
        if any(not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'] for item in items):
            raise ValueError('Each protocol item needs a nonempty string ID.')
        text_keys = ('label',) if key == 'supplies' else ('title', 'detail')
        if any(any(not isinstance(item.get(field), str) or not item[field].strip() or len(item[field]) > 160 for field in text_keys) for item in items):
            raise ValueError('Protocol text must contain 1–160 characters.')
        if any('warning' in item and (not isinstance(item['warning'], str) or len(item['warning']) > 160) for item in items):
            raise ValueError('Protocol warnings must be text of at most 160 characters.')
        ids = [item['id'] for item in items]
        if len(set(ids)) != len(ids):
            raise ValueError('Protocol IDs must be unique.')
    if not isinstance(data.get('medication'), str) or not 1 <= len(data['medication']) <= 80:
        raise ValueError('Protocol medication title must contain 1–80 characters.')
    target, tolerance = data.get('target_volume_ml'), data.get('tolerance_ml')
    if (target is None) != (tolerance is None):
        raise ValueError('Configure both target volume and tolerance, or neither.')
    if target is not None and (any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in (target, tolerance)) or target <= 0 or tolerance <= 0 or tolerance >= target):
        raise ValueError('Target and tolerance must be finite positive values; tolerance must be below target.')
    return data


class Session:
    def __init__(self, station, protocol=None, log_path=None, max_age=60):
        self.station = station
        self.protocol = deepcopy(protocol or load_protocol())
        self.log_path = Path(log_path or station.log_path.with_name('session-events.jsonl'))
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_age = max_age
        self.lock = threading.RLock()
        self.worker = None
        self.revision = 0
        self._reset()

    def _reset(self):
        self.id = uuid.uuid4().hex
        self.screen = 'start'
        self.supply_index = self.prep_index = 0
        self.confirmed = []
        self.missing = False
        self.help_open = self.seated = False
        self.focus_action = None
        self.result = None
        self.checked_at = None
        self.check_id = None
        self.seat_started_at = None
        self.revision += 1

    def _log(self, event, **details):
        record = dict(event=event, timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                      session_id=self.id, revision=self.revision, **details)
        try:
            with self.log_path.open('a') as stream:
                stream.write(json.dumps(record, allow_nan=False) + '\n')
        except OSError as exc:
            raise FlowError('Cannot save station events. Check device storage.', 503) from exc

    def _invalidate(self):
        self.result = self.checked_at = self.check_id = None
        self.station.preview = None

    def _freshness(self):
        if self.result is None or self.screen not in {'result', 'done'}:
            return
        try:
            seated = self.station.read_seat(self.seated)
            moved = self.result.get('seat_generation') is not None and getattr(self.station.seat, 'generation', None) != self.result['seat_generation']
        except Exception:
            seated, moved = None, True
        if moved or (self.result.get('syringe_seated') is True and seated is not True) or self.checked_at is None or time.monotonic() - self.checked_at > self.max_age:
            self._invalidate()
            self.screen = 'check'
            self.revision += 1

    def snapshot(self):
        with self.lock:
            self._freshness()
            return deepcopy(dict(session_id=self.id, revision=self.revision, screen=self.screen,
                                 supply_index=self.supply_index, prep_index=self.prep_index,
                                 confirmed=self.confirmed, missing=self.missing, help_open=self.help_open,
                                 seated=self.seated, simulated=self.station.simulated, focus_action=self.focus_action,
                                 hardware_seat=self.station.seat is not None,
                                 busy=self.worker is not None and self.worker.is_alive(),
                                 result=self.result, check_id=self.check_id,
                                 protocol=self.protocol,
                                 mode=self.station.camera.mode, model_version=self.station.engine.metadata['version']))

    def action(self, action, session_id, revision):
        if not isinstance(action, str):
            raise FlowError('Action must be a string.', 400)
        with self.lock:
            self._freshness()
            if session_id != self.id or type(revision) is not int or revision != self.revision:
                raise FlowError('Station changed. Refresh and try again.')
            if action == 'reset':
                self._log('session_reset')
                self._reset()
                return self.snapshot()
            if action in {'help', 'close_help'}:
                self._log(action)
                self.help_open = action == 'help'
                self.revision += 1
                return self.snapshot()
            if self.help_open:
                raise FlowError('Close help before continuing.')
            allowed = {
                'start': {'begin'}, 'supplies': {'confirm', 'missing', 'back'},
                'prep': {'next', 'back'}, 'check': {'capture', 'back'},
                'checking': set(), 'result': {'retry', 'complete'}, 'done': set(),
            }[self.screen]
            if self.screen == 'check' and self.station.simulated:
                allowed = allowed | {'seat'}
            if action not in allowed:
                raise FlowError('Action unavailable on this screen.')
            if action == 'complete' and (not self.result or self.result['verdict'] != 'pass'):
                raise FlowError('A complete, current volume and air check is required.')
            if action == 'capture' and (self.station.lock.locked() or (self.worker is not None and self.worker.is_alive())):
                raise FlowError('A capture is already running.')
            self._log(action)
            self.focus_action = None
            if action == 'begin':
                self.screen = 'supplies'
            elif action == 'confirm':
                self.confirmed.append(self.protocol['supplies'][self.supply_index]['id'])
                self.supply_index += 1
                self.missing = False
                if self.supply_index == len(self.protocol['supplies']):
                    self.screen = 'prep'
            elif action == 'missing':
                self.missing = True
            elif action == 'next':
                self.prep_index += 1
                if self.prep_index == len(self.protocol['prep_steps']):
                    self.screen = 'check'
            elif action == 'back':
                self._invalidate()
                if self.screen == 'check':
                    self.screen, self.prep_index = 'prep', len(self.protocol['prep_steps']) - 1
                elif self.screen == 'prep':
                    if self.prep_index:
                        self.prep_index -= 1
                    else:
                        self.screen, self.supply_index = 'supplies', len(self.confirmed) - 1
                        self.confirmed.pop()
                elif self.missing:
                    self.missing = False
                elif self.supply_index:
                    self.supply_index -= 1
                    self.confirmed.pop()
                else:
                    self.screen = 'start'
            elif action == 'seat':
                self.seated = not self.seated
                self._invalidate()
            elif action == 'retry':
                self._invalidate()
                self.screen, self.seated = 'check', False
            elif action == 'complete':
                self.screen = 'done'
            elif action == 'capture':
                self._invalidate()
                self.check_id = uuid.uuid4().hex
                try:
                    self.seat_started_at = getattr(self.station.seat, 'seated_at', None) if self.station.seat is not None else time.monotonic()
                except Exception:
                    self.seat_started_at = None
                self.screen = 'checking'
                self.worker = threading.Thread(target=self._capture, args=(self.id, self.check_id, self.seated), daemon=True)
                self.worker.start()
            self.revision += 1
            return self.snapshot()

    def _capture(self, session_id, check_id, seated):
        try:
            measurement, code = self.station.check(seated, session_id=session_id, check_id=check_id)
            result = self._verdict(measurement)
            if code != 200:
                result.update(verdict='unable', reason=measurement.get('message', 'Check failed.'), reason_code='acquisition_failed')
        except Exception:
            result = dict(verdict='unable', reason_code='acquisition_failed', reason='Station could not complete the check.', action='Check device storage and retry.', volume_ml=None, air_ml=None)
        with self.lock:
            if self.id != session_id or self.check_id != check_id:
                return
            try:
                self._log('check_finished', check_id=check_id, result=result)
            except FlowError:
                result.update(verdict='unable', reason='Cannot save the result. Check device storage.', reason_code='storage_unavailable')
            self.result = result
            self.screen = 'result'
            self.checked_at = time.monotonic()
            self.revision += 1

    def _verdict(self, measurement):
        result = dict(measurement, verdict='unable', reason_code='acquisition_failed', reason=measurement.get('message', 'Check incomplete.'), action='Correct the issue and check again.')
        if measurement.get('state') not in {'air_detected', 'no_air_detected'}:
            if len(result['reason']) > 120:
                result['reason'] = 'The station could not verify this check. See the device log.'
            return result
        if measurement.get('air_detected') is True:
            result.update(verdict='fix', reason_code='air_detected', reason='Visible air detected.', action='Follow the agreed bench correction procedure, then recheck.')
            return result
        volume = measurement.get('volume_ml')
        target, tolerance = self.protocol.get('target_volume_ml'), self.protocol.get('tolerance_ml')
        if not measurement.get('valid') or volume is None or isinstance(volume, bool) or not isinstance(volume, (float, int)) or not math.isfinite(volume) or volume < 0 or target is None or tolerance is None:
            result.update(reason_code='volume_unverified', reason='No visible air detected; volume not verified.', action='Volume calibration and a target/tolerance are required for a combined check.')
        elif abs(volume - target) > tolerance:
            result.update(verdict='fix', reason_code='volume_out_of_tolerance', reason='Measured barrel volume is outside the configured tolerance.', action='Adjust according to the agreed bench protocol and recheck.')
        elif measurement.get('air_detected') is False and measurement.get('syringe_seated') is True:
            result.update(verdict='pass', reason_code='checks_passed', reason='Configured bench volume and visible-air checks passed.', action='Experimental bench result; not injection clearance.')
        return result

    def encoder_event(self, event, expected=None):
        # Use the same actions presented by the native view, with no second flow.
        from .touchscreen import view
        with self.lock:
            state = self.snapshot()
            if expected is not None and expected != (state['session_id'], state['revision']):
                raise FlowError('Stale encoder press discarded.')
            choices = [button['action'] for button in view(state)['buttons']]
            if event not in {'next', 'previous', 'press'}:
                raise FlowError('Unknown encoder event.', 400)
            if not choices:
                return
            if event == 'press' and self.focus_action in choices:
                self.action(self.focus_action, state['session_id'], state['revision'])
                return
            if self.focus_action not in choices:
                # First press highlights the primary control; a second press activates.
                self.focus_action = choices[-1] if event == 'press' else choices[0]
            else:
                index = choices.index(self.focus_action)
                self.focus_action = choices[(index + (1 if event == 'next' else -1)) % len(choices)]
            self.revision += 1

    def supplies(self):
        with self.lock:
            return {'source': 'manual confirmation', 'holders': {item['id']: {'present': None, 'correct': None, 'confirmed': item['id'] in self.confirmed} for item in self.protocol['supplies']}}

    def log_client_event(self, event, check_id=None):
        if not isinstance(event, str) or not 1 <= len(event) <= 100:
            raise FlowError('Event must contain 1–100 characters.', 400)
        with self.lock:
            if event in {'result_displayed', 'native_result_displayed'}:
                self._freshness()
                if not self.result or check_id != self.check_id:
                    raise FlowError('Display acknowledgement is for an expired check.')
                elapsed = (time.monotonic() - self.seat_started_at) * 1000 if self.seat_started_at is not None else None
                self._log('ui_event', name=event, check_id=check_id, seat_to_display_ack_ms=round(elapsed, 1) if elapsed is not None else None)
            else:
                self._log('ui_event', name=event)

    def close(self):
        # Invalidate any outstanding result before orderly resource shutdown.
        with self.lock:
            self._reset()
        if self.worker is not None:
            self.worker.join(timeout=30)
        self.station.close()
