from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np

from medlock_lab.imaging import PREPROCESS_VERSION, tensor_array
from .acquisition import Acquisition


class Engine:
    """ONNX feature extractor + the unchanged fitted logistic-regression head."""
    def __init__(self, bundle: Path, threads=2):
        bundle = Path(bundle)
        self.metadata = json.loads((bundle / 'manifest.json').read_text())
        threshold = self.metadata.get('threshold')
        if type(threshold) not in (float, int) or not math.isfinite(threshold) or not 0 < threshold < 1:
            raise ValueError('Model threshold must be finite and between zero and one.')
        if self.metadata.get('input_shape') != [1, 3, 224, 224] or not self.metadata.get('version'):
            raise ValueError('Unsupported model input shape or missing version.')
        if set(self.metadata.get('sha256', {})) != {'features.onnx', 'classifier.json'}:
            raise ValueError('Model manifest must hash both inference files.')
        if self.metadata['preprocess_version'] != PREPROCESS_VERSION:
            raise ValueError('Model and image preprocessing versions do not match.')
        for name, digest in self.metadata['sha256'].items():
            if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f'Model checksum mismatch: {name}')
        self.parameters = json.loads((bundle / 'classifier.json').read_text())
        arrays = [np.asarray(self.parameters[key], dtype=np.float64) for key in ('mean', 'scale', 'coef')]
        if any(a.ndim != 1 or len(a) != 1280 or not np.isfinite(a).all() for a in arrays) or np.any(arrays[1] <= 0):
            raise ValueError('Invalid classifier parameters.')
        if type(self.parameters.get('intercept')) not in (int, float) or not math.isfinite(self.parameters['intercept']):
            raise ValueError('Invalid classifier intercept.')
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
    simulated = True
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
    simulated = False
    mode = 'Pi CSI camera — rpicam-still'
    def capture(self):
        result = subprocess.run(['rpicam-still', '--nopreview', '--timeout', '1500',
                                 '--autofocus-mode', 'auto', '--width', '1296', '--height', '972',
                                 '--encoding', 'jpg', '--output', '-'],
                                capture_output=True, timeout=20, check=True)
        return result.stdout, 'pi-camera.jpg'


# Public compatibility name; acquisition is implemented in one place.
Station = Acquisition
