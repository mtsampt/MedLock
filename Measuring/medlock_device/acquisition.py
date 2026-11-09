"""One owner for capture, lighting, image processing and inference."""
from __future__ import annotations

import json
import hashlib
import uuid
import math
import threading
import time
from pathlib import Path

from medlock_lab.imaging import ImageProblem, clean, decode
from .measurement import Measurement


class Acquisition:
    def __init__(self, engine, camera, log_path, rotation=0, seat=None, light=None, volume=None, capture_dir=None):
        self.engine, self.camera = engine, camera
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.rotation, self.seat, self.light, self.volume = rotation, seat, light, volume
        self.lock = threading.Lock()
        self.preview = None
        self.result = {'state': 'waiting', 'message': 'Seat the syringe, then capture.'}
        self.closed = False
        self.capture_dir = Path(capture_dir) if capture_dir is not None else None
        if self.capture_dir is not None:
            self.capture_dir.mkdir(parents=True, exist_ok=True)

    @property
    def simulated(self):
        return getattr(self.camera, 'simulated', False) is True

    def read_seat(self, simulated_seated=False):
        if self.seat is not None:
            return bool(self.seat.is_pressed)
        return simulated_seated is True if self.simulated else None

    def check(self, simulated_seated=False, session_id=None, check_id=None):
        if not self.lock.acquire(blocking=False):
            return {'state': 'busy', 'message': 'A capture is already running.'}, 409
        started = time.monotonic()
        self.preview = None
        self.result = {'state': 'checking', 'message': 'Checking syringe.'}
        result = Measurement(rotation=self.rotation, mode=self.camera.mode, session_id=session_id, check_id=check_id,
                             seat_mode='GPIO' if self.seat is not None else ('simulation' if self.simulated else 'unavailable'),
                             model_version=self.engine.metadata['version'])
        calibration = getattr(self.volume, 'calibration', {})
        result.calibration_version = getattr(self.volume, 'version', None)
        result.syringe_profile = calibration.get('syringe_id')
        result.setup_id = calibration.get('setup_id')
        light_attempted = False
        seated_at = None
        code = 200
        try:
            if self.closed:
                raise ImageProblem('Station is shutting down.')
            result.syringe_seated = self.read_seat(simulated_seated)
            if result.syringe_seated is not True:
                raise ImageProblem('Seat sensor unavailable.' if result.syringe_seated is None else 'Syringe is not seated. Previous result cleared.')
            result.seat_generation = getattr(self.seat, 'generation', None)
            seated_at = getattr(self.seat, 'seated_at', started) if self.seat is not None else started
            if self.light is not None:
                light_attempted = True
                self.light.on()
                time.sleep(.2)
            self._require_seated(result, simulated_seated)
            data, result.source = self.camera.capture()
            result.source_sha256 = hashlib.sha256(data).hexdigest()
            if self.capture_dir is not None:
                suffix = Path(result.source).suffix.lower()
                suffix = suffix if suffix in {'.jpg', '.jpeg', '.png', '.webp'} else '.bin'
                capture = self.capture_dir / (uuid.uuid4().hex + suffix)
                with capture.open('xb') as stream:
                    stream.write(data)
                result.capture_file = str(capture)
            image = decode(data).rotate(self.rotation, expand=True)
            processed, result.image_quality = clean(image)
            self.preview = processed
            if result.image_quality['warnings']:
                raise ImageProblem('Image is too soft. Refocus and capture again.')
            self._require_seated(result, simulated_seated)
            infer_start = time.perf_counter()
            prediction = self.engine.predict(processed)
            if prediction.get('label') not in {'air', 'no_air'} or type(prediction.get('air_score')) not in (int, float) or not math.isfinite(prediction['air_score']) or not 0 <= prediction['air_score'] <= 1:
                raise ImageProblem('Invalid model response.')
            result.inference_ms = round((time.perf_counter() - infer_start) * 1000, 1)
            result.label, result.air_score = prediction['label'], prediction['air_score']
            result.air_detected = result.label == 'air'
            if self.volume is not None:
                try:
                    result.volume_ml = self.volume.estimate(image, result.image_quality)
                    if type(result.volume_ml) not in (int, float) or not math.isfinite(result.volume_ml) or result.volume_ml < 0:
                        result.volume_ml = None
                        raise ValueError('Volume unavailable: invalid estimate.')
                    result.volume_status = 'calibrated occupied barrel volume'
                    result.volume_method = 'stopper position; not air volume subtraction'
                except ValueError as exc:
                    result.volume_status = str(exc)
            self._require_seated(result, simulated_seated)
            result.valid = type(result.volume_ml) in (int, float) and math.isfinite(result.volume_ml) and result.volume_ml >= 0
            result.state = 'air_detected' if result.air_detected else 'no_air_detected'
            result.message = 'Visible air detected' if result.air_detected else 'No visible air detected'
        except Exception as exc:
            result.state, result.valid = 'unable', False
            result.label = result.air_score = result.air_detected = result.volume_ml = None
            result.error = f'{type(exc).__name__}: {exc}'
            result.message = str(exc) if isinstance(exc, (ImageProblem, ValueError)) else 'Camera or inference failed. Check the device log and retry.'
        finally:
            if light_attempted:
                try:
                    self.light.off()
                except Exception as exc:
                    result.state, result.valid = 'unable', False
                    result.label = result.air_score = result.air_detected = result.volume_ml = None
                    result.message, result.error = 'Backlight control failed.', str(exc)
            result.elapsed_ms = round((time.monotonic() - started) * 1000, 1)
            if seated_at is not None:
                result.seat_to_result_ms = round((time.monotonic() - seated_at) * 1000, 1)
            result.timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            payload = result.as_dict()
            try:
                with self.log_path.open('a') as log:
                    log.write(json.dumps(payload, allow_nan=False) + '\n')
            except OSError:
                payload.update(state='unable', valid=False, label=None, air_score=None, air_detected=None,
                               volume_ml=None, message='Cannot save the result. Check device storage.', error='event_storage_unavailable')
                code = 503
            finally:
                self.result = payload
                self.lock.release()
        return payload, code

    def _require_seated(self, result, simulated_seated):
        result.syringe_seated = self.read_seat(simulated_seated)
        moved = result.seat_generation is not None and getattr(self.seat, 'generation', None) != result.seat_generation
        if result.syringe_seated is not True or moved:
            raise ImageProblem('Syringe moved during capture or processing. Capture again.')

    def close(self):
        # Wait for the bounded camera/inference worker before closing GPIO.
        with self.lock:
            self.closed = True
            failures = []
            try:
                if self.light is not None:
                    self.light.off()
            except Exception as exc:
                failures.append(exc)
            for resource in (self.light, self.seat):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception as exc:
                        failures.append(exc)
            if failures:
                raise RuntimeError('Station resource cleanup failed.') from failures[0]
