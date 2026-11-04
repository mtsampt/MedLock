"""Shared deterministic preprocessing for seed images, uploads, and inference."""
from __future__ import annotations

import hashlib
import io
import warnings
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

PREPROCESS_VERSION = 'barrel-v1-224'
Image.MAX_IMAGE_PIXELS = 30_000_000


class ImageProblem(ValueError):
    pass


def decode(data: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ImageProblem('Use a JPG, PNG, or WebP photo. Export HEIC photos to JPG first.')
                if getattr(source, 'n_frames', 1) != 1:
                    raise ImageProblem('Use a single still image.')
                im = ImageOps.exif_transpose(source).convert('RGB')
                if min(im.size) < 300:
                    raise ImageProblem('This photo is too small. Upload an original at least 300 pixels on each side.')
                return im
    except ImageProblem:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, ValueError) as exc:
        raise ImageProblem('Could not read this image. Use an original JPG, PNG, or WebP photo.') from exc


def pixel_hash(im: Image.Image) -> str:
    return hashlib.sha256(str(im.size).encode() + im.tobytes()).hexdigest()


def clean(im: Image.Image) -> tuple[Image.Image, dict]:
    """Find the dark stopper in upright, tip-down photos, then crop the fluid side.

    This deliberately supports similar framing to the pilot, not arbitrary photos.
    No smoothing, generative edits, or selective bubble enhancement is applied.
    """
    w, h = im.size
    if w > h:
        raise ImageProblem('Use a portrait photo with the plunger at the top and tip at the bottom, like the pilot photos.')
    scale = min(1.0, 1200 / h)
    small = np.asarray(im.resize((round(w * scale), round(h * scale))))
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    sh, sw = gray.shape
    search = np.zeros_like(gray)
    search[round(sh*.23):round(sh*.80), round(sw*.28):round(sw*.72)] = 1
    mask = ((gray < 100) & (search > 0)).astype('uint8') * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        center = (x + bw/2) / sw
        if .055*sw < bw < .32*sw and .006*sh < bh < .095*sh and bw/bh > 1.2 and .35 < center < .65:
            candidates.append((cv2.contourArea(contour), x, y, bw, bh))
    if not candidates:
        raise ImageProblem('Cannot locate the dark rubber stopper. Use similar framing, sharper focus, and even lighting.')
    _, x, y, bw, bh = max(candidates)
    # Retain the full cross-section just beyond the stopper, down to the tip area.
    cx = (x + bw/2) / scale
    diameter = bw / scale
    left = max(0, round(cx - diameter*.60))
    right = min(w, round(cx + diameter*.60))
    top = round((y+bh) / scale - diameter*.025)
    bottom = min(round(h*.82), round(top + diameter*5.2))
    if bottom - top < diameter*.9:
        raise ImageProblem('Too little barrel is visible below the stopper. Include the entire fluid-filled region.')
    crop = im.crop((left, top, right, bottom))
    fitted = ImageOps.contain(crop, (224, 224), Image.Resampling.LANCZOS)
    # The padding is constant and independent of the label.
    processed = Image.new('RGB', (224, 224), (128, 128, 128))
    processed.paste(fitted, ((224-fitted.width)//2, (224-fitted.height)//2))
    sharpness = float(cv2.Laplacian(cv2.cvtColor(np.asarray(crop.resize((224, 448))), cv2.COLOR_RGB2GRAY), cv2.CV_64F).var())
    messages = []
    if sharpness < 18:
        messages.append('Soft focus: small bubbles may be missed. Consider a sharper photo.')
    return processed, {
        'version': PREPROCESS_VERSION, 'original_width': w, 'original_height': h,
        'crop_box': [left, top, right, bottom], 'stopper_box': [round(x/scale), round(y/scale), round(bw/scale), round(bh/scale)],
        'sharpness': round(sharpness, 2), 'warnings': messages,
        'crop_note': 'Automatic crop. Check that all liquid and suspected air are included.',
    }


def tensor_array(im: Image.Image) -> np.ndarray:
    a = np.asarray(im, dtype=np.float32) / 255.0
    a = (a - np.array([.485, .456, .406], np.float32)) / np.array([.229, .224, .225], np.float32)
    return a.transpose(2, 0, 1).copy()
