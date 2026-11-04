from __future__ import annotations

import hashlib
import json
import math
import subprocess
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from medlock_lab.imaging import PREPROCESS_VERSION, ImageProblem, clean, decode, tensor_array


class Engine:
    """ONNX feature extractor + the unchanged fitted logistic-regression head."""
    def __init__(self, bundle: Path, threads=2):
        self.metadata = json.loads((bundle / 'manifest.json').read_text())
        if self.metadata['preprocess_version'] != PREPROCESS_VERSION:
            raise ValueError('Model and image preprocessing versions do not match.')
        for name, digest in self.metadata['sha256'].items():
            if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f'Model checksum mismatch: {name}')
        self.parameters = json.loads((bundle / 'classifier.json').read_text())
        cv2.setNumThreads(threads)
        self.net = cv2.dnn.readNetFromONNX(str(bundle / 'features.onnx'))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    def predict(self, processed):
        self.net.setInput(tensor_array(processed)[None])
        features = self.net.forward().reshape(-1).astype(np.float64)
        if not np.isfinite(features).all():
            raise ValueError('Model produced invalid image features.')
        p = self.parameters
        z = float(np.dot((features - np.array(p['mean'])) / np.array(p['scale']), p['coef']) + p['intercept'])
        if not math.isfinite(z):
            raise ValueError('Model produced an invalid score.')
        score = 1 / (1 + math.exp(-float(np.clip(z, -40, 40))))
        return {'label': 'air' if score >= self.metadata['threshold'] else 'no_air',
                'air_score': round(score, 5)}


class ReplayCamera:
    mode = 'photo replay — simulated hardware'
    def __init__(self, directory):
        self.files = sorted(p for p in Path(directory).iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'})
        if not self.files:
            raise ValueError('Replay directory has no supported photos.')
        self.index = 0

    def capture(self):
        path = self.files[self.index % len(self.files)]
        self.index += 1
        return path.read_bytes(), path.name


class PiCamera:
    mode = 'Pi CSI camera — rpicam-still'
    def capture(self):
        result = subprocess.run(['rpicam-still', '--nopreview', '--timeout', '1500',
                                 '--autofocus-mode', 'auto', '--width', '1296', '--height', '972',
                                 '--encoding', 'jpg', '--output', '-'],
                                capture_output=True, timeout=20, check=True)
        return result.stdout, 'pi-camera.jpg'


class Station:
    def __init__(self, engine, camera, log_path, rotation=0, seat=None, light=None):
        self.engine, self.camera = engine, camera
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.rotation, self.seat, self.light = rotation, seat, light
        self.lock = threading.Lock()
        self.preview = None
        self.result = {'state': 'waiting', 'message': 'Seat the syringe, then capture.'}

    def check(self, simulated_seated):
        if not self.lock.acquire(blocking=False):
            return {'state': 'busy', 'message': 'A capture is already running.'}, 409
        started = time.perf_counter()
        self.preview = None
        result = {'state': 'unable', 'label': None, 'air_score': None,
                  'volume_ml': None, 'volume_status': 'not implemented',
                  'mode': self.camera.mode,
                  'seat_mode': 'GPIO' if self.seat else 'manual simulation',
                  'model_version': self.engine.metadata['version']}
        light_on = False
        try:
            is_seated = lambda: bool(self.seat.is_pressed) if self.seat else simulated_seated
            if not is_seated():
                raise ImageProblem('Syringe is not seated. Previous result cleared.')
            if self.light:
                self.light.on()
                light_on = True
                time.sleep(.2)
            data, name = self.camera.capture()
            result['source'] = name
            im = decode(data).rotate(self.rotation, expand=True)
            processed, quality = clean(im)
            self.preview = processed
            result['image_quality'] = quality
            if quality['warnings']:
                raise ImageProblem('Image is too soft. Refocus and capture again.')
            if not is_seated():
                raise ImageProblem('Syringe moved during capture. Capture again.')
            infer_start = time.perf_counter()
            prediction = self.engine.predict(processed)
            result['inference_ms'] = round((time.perf_counter() - infer_start) * 1000, 1)
            if not is_seated():
                raise ImageProblem('Syringe moved during processing. Capture again.')
            result.update(prediction)
            result['state'] = 'air_detected' if prediction['label'] == 'air' else 'no_air_detected'
            result['message'] = ('Visible air detected' if prediction['label'] == 'air' else 'No visible air detected')
        except (ImageProblem, ValueError) as exc:
            result['message'] = str(exc)
        except Exception as exc:
            result['message'] = 'Camera or inference failed. Check the device log and retry.'
            result['error'] = f'{type(exc).__name__}: {exc}'
        finally:
            if light_on:
                try:
                    self.light.off()
                except Exception:
                    result.update(state='unable', label=None, air_score=None, message='Backlight control failed.')
            result['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 1)
            result['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            self.result = result
            try:
                with self.log_path.open('a') as log:
                    log.write(json.dumps(result) + '\n')
            finally:
                self.lock.release()
        return result, 200
