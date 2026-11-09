"""Fit/evaluate a fixed-dock volume calibration using independently labelled fills.

CSV columns: image, volume_ml, session, split, air_free
split is train or evaluate; air_free must be true. Paths are relative to CSV.
No files are relabelled or assigned to sessions automatically.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from medlock_lab.imaging import PREPROCESS_VERSION, clean, decode, pixel_hash
from medlock_device.volume import geometry


def calibrate(manifest, setup_id, syringe_id, max_error, geometry_margin, rotation=0):
    if not setup_id.strip() or not syringe_id.strip() or not math.isfinite(max_error) or max_error <= 0 or not math.isfinite(geometry_margin) or not 0 < geometry_margin < .1:
        raise ValueError('Provide setup/syringe IDs, positive error bound and geometry margin between 0 and 0.1.')
    records, hashes, sizes = [], set(), set()
    for row in csv.DictReader(manifest.open()):
        if row['split'] not in {'train', 'evaluate'} or not row['session'].strip() or row['air_free'].lower() != 'true':
            raise ValueError('Each row needs split, true air_free and a real collection session.')
        volume = float(row['volume_ml'])
        if not math.isfinite(volume) or volume < 0:
            raise ValueError('Reference volumes must be measured finite nonnegative values.')
        image = decode((manifest.parent / row['image']).read_bytes()).rotate(rotation, expand=True)
        digest = pixel_hash(image)
        if digest in hashes:
            raise ValueError('Duplicate image pixels in calibration manifest.')
        hashes.add(digest)
        sizes.add(image.size)
        _, quality = clean(image)
        if quality['warnings']:
            raise ValueError(f"Rejected calibration image: {row['image']}")
        records.append(dict(features=geometry(image, quality), volume=volume, split=row['split'], session=row['session']))
    train = [row for row in records if row['split'] == 'train']
    evaluate = [row for row in records if row['split'] == 'evaluate']
    train_sessions = sorted({r['session'] for r in train})
    eval_sessions = sorted({r['session'] for r in evaluate})
    if len(sizes) != 1 or len(train) < 6 or len(evaluate) < 3 or len(train_sessions) < 2 or not eval_sessions or set(train_sessions) & set(eval_sessions):
        raise ValueError('Need one resolution, >=6 training images across >=2 sessions, and >=3 evaluation images from separate sessions.')
    if any(len({r['volume'] for r in rows}) < 3 for rows in (train, evaluate)):
        raise ValueError('Train and evaluation sets each need >=3 distinct reference fills.')
    x = np.array([r['features'] for r in train])
    y = np.array([r['volume'] for r in train])
    if np.ptp(x[:, 0]) < .01:
        raise ValueError('Training stopper positions need a measurable range.')
    slope, intercept = np.polyfit(x[:, 0], y, 1)
    if slope >= 0:
        raise ValueError('Calibration must use upright tip-down syringe geometry.')
    lower, upper = x.min(axis=0), x.max(axis=0)
    # Position stays interpolation-only; allow an explicit alignment/width margin.
    lower[1:] -= geometry_margin
    upper[1:] += geometry_margin
    errors = []
    for row in evaluate:
        f = row['features']
        if np.any(f < lower) or np.any(f > upper):
            raise ValueError('Evaluation geometry is outside the training envelope.')
        estimate = float(slope * f[0] + intercept)
        errors.append(abs(estimate - row['volume']))
    if max(errors) > max_error:
        raise ValueError(f'Held-out maximum error {max(errors):.4f} mL exceeds {max_error:.4f} mL. No calibration exported.')
    return dict(version=1, preprocess_version=PREPROCESS_VERSION, setup_id=setup_id, syringe_id=syringe_id,
                measurement='occupied_barrel_ml', image_size=list(next(iter(sizes))), rotation=rotation,
                slope=float(slope), intercept=float(intercept), max_error_ml=max_error,
                feature_min=lower.tolist(), feature_max=upper.tolist(), volume_range_ml=[float(y.min()), float(y.max())],
                training_sessions=train_sessions, training_count=len(train),
                evaluation=dict(count=len(evaluate), sessions=eval_sessions, max_error_ml=max(errors), mean_error_ml=float(np.mean(errors))),
                manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), image_pixel_hashes=sorted(hashes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--setup-id', required=True)
    parser.add_argument('--syringe-id', required=True)
    parser.add_argument('--max-error-ml', required=True, type=float)
    parser.add_argument('--geometry-margin', required=True, type=float, help='Normalized x/width alignment margin; <0.1')
    parser.add_argument('--rotation', type=int, choices=[0, 90, 180, 270], default=0)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = calibrate(args.manifest, args.setup_id, args.syringe_id, args.max_error_ml, args.geometry_margin, args.rotation)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result['evaluation'], indent=2))


if __name__ == '__main__':
    main()
