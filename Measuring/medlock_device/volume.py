"""Calibrated occupied barrel volume from the fluid-side stopper edge.

This measures geometry, not liquid-minus-air volume. Supports one fixed syringe,
resolution, orientation and dock setup. No calibration is bundled by default.
"""
from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
import numpy as np

from medlock_lab.imaging import PREPROCESS_VERSION


def geometry(image, quality):
    box = quality.get('stopper_box')
    if not isinstance(box, list) or len(box) != 4 or any(type(v) not in (float, int) or not math.isfinite(v) for v in box):
        raise ValueError('Volume unavailable: stopper geometry missing.')
    x, y, width, height = box
    w, h = image.size
    if min(width, height) <= 0 or min(x, y) < 0 or x + width > w or y + height > h:
        raise ValueError('Volume unavailable: invalid stopper geometry.')
    return np.array([(y + height) / h, (x + width / 2) / w, width / w], dtype=float)


class VolumeEstimator:
    def __init__(self, path, setup_id):
        raw = Path(path).read_bytes()
        self.version = hashlib.sha256(raw).hexdigest()
        self.calibration = c = json.loads(raw)
        if c.get('version') != 1 or c.get('preprocess_version') != PREPROCESS_VERSION or not setup_id or c.get('setup_id') != setup_id:
            raise ValueError('Volume calibration version/setup does not match this station.')
        if type(c.get('rotation')) is not int or c['rotation'] not in (0, 90, 180, 270):
            raise ValueError('Invalid calibration rotation.')
        if not c.get('syringe_id') or c.get('measurement') != 'occupied_barrel_ml':
            raise ValueError('Unsupported volume calibration.')
        try:
            numbers = [c['slope'], c['intercept'], c['max_error_ml'], c['evaluation']['max_error_ml'],
                       *c['image_size'], *c['feature_min'], *c['feature_max'], *c['volume_range_ml']]
            if any(type(x) not in (int, float) or not math.isfinite(x) for x in numbers):
                raise ValueError('Invalid calibration numbers.')
            if len(c['image_size']) != 2 or any(type(x) is not int or x < 300 for x in c['image_size']):
                raise ValueError('Invalid calibration resolution.')
            if len(c['feature_min']) != 3 or len(c['feature_max']) != 3 or any(a >= b for a, b in zip(c['feature_min'], c['feature_max'])):
                raise ValueError('Invalid calibration geometry range.')
            if c['slope'] >= 0 or c['max_error_ml'] <= 0 or not 0 <= c['evaluation']['max_error_ml'] <= c['max_error_ml']:
                raise ValueError('Calibration did not meet its error bound.')
            if c['evaluation']['count'] < 3 or len(c['training_sessions']) < 2 or not c['evaluation']['sessions'] or set(c['training_sessions']) & set(c['evaluation']['sessions']):
                raise ValueError('Independent calibration sessions required.')
            if len(c['volume_range_ml']) != 2 or not 0 <= c['volume_range_ml'][0] < c['volume_range_ml'][1]:
                raise ValueError('Invalid calibration volume range.')
        except (KeyError, TypeError) as exc:
            raise ValueError('Incomplete calibration file.') from exc

    def estimate(self, image, quality):
        c = self.calibration
        if list(image.size) != c['image_size']:
            raise ValueError('Volume unavailable: camera resolution does not match calibration.')
        features = geometry(image, quality)
        if np.any(features < c['feature_min']) or np.any(features > c['feature_max']):
            raise ValueError('Volume unavailable: syringe geometry outside calibration.')
        volume = float(c['slope'] * features[0] + c['intercept'])
        if not math.isfinite(volume) or not c['volume_range_ml'][0] - 1e-9 <= volume <= c['volume_range_ml'][1] + 1e-9:
            raise ValueError('Volume unavailable: outside calibrated range.')
        return float(np.clip(volume, *c['volume_range_ml']))
