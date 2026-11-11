# MedLock Image Lab

**Setting up the Raspberry Pi?** Start with the [copy-and-paste Pi instructions in the main README](../README.md#raspberry-pi-copy-and-paste-setup). The laptop training instructions below are separate from the Pi runtime.

A local bench prototype for classifying **visible air / no visible air** in water-filled syringe photos. The first dataset contains 27 photos (18 air, 9 no visible air). The six previously ambiguous negatives use Matt's confirmation.

## Open the app

Double-click `Start MedLock.command`, or run from this project directory:

```sh
.venv/bin/python -m medlock_lab serve
```

Open <http://127.0.0.1:8765>. The server binds to your computer's loopback address. Image upload, prediction, labeling and retraining run locally. The initial pretrained backbone download requires internet; prediction and retraining work offline once the weights exist.

## Use

1. Drop a JPG, PNG or WebP photo into **Test a photo**. HEIC must first be exported to JPG.
2. Inspect both the original and **What the model sees**. This version expects similar portrait framing, plunger at top, tip at bottom. The entire fluid region must be included. Unsupported framing is rejected rather than guessed.
3. Read the experimental prediction. A score is a model output, not a calibrated probability.
4. Click **Air** or **No visible air** to supply the correct label. The prediction is never automatically used as a label.
5. Click **Train with new data**. This retrains on the full labeled dataset, including previous photos and new/corrected labels. The previous model remains available until training succeeds.
6. Click any library image to review or correct its label. New labels are queued; they do not silently alter the current model. An image from the training set is explicitly marked as such.

Change **Collection session** when you start a different collection sitting. Do not invent different sessions for adjacent photos of the same preparation. Exact pixel duplicates are merged, even with different filenames. Near-duplicates are not automatically merged, so session grouping remains important.

## What is implemented

- EXIF orientation correction, rubber-stopper localization, fluid-side barrel crop, aspect-preserving 224×224 resize with fixed padding, ImageNet mean/std normalization.
- Original image bytes are preserved. No smoothing or generative enhancement is applied. Crops and previews are separate derivatives.
- Frozen **MobileNetV2 ImageNet V2** features and balanced L2-regularized logistic regression (`C=0.03`, fixed before evaluation). Only the small classifier is fitted to the pilot.
- Feature cache keyed by oriented image pixels and preprocessing version.
- Grouped checks hold out entire pilot fill blocks. With multiple collection sessions, evaluation holds out entire sessions. Scaling and classifier fitting use training folds only. The deployed model is subsequently fitted on all labeled images.
- Versioned model reports and snapshot/revision tracking. A label saved during training remains queued if it was not in the training snapshot. Failed training leaves the active model unchanged.
- A standalone TorchScript CPU model (`model_cpu.pt`) includes the backbone and classifier. Its input is a batch of normalized RGB tensors `[N,3,224,224]`; output is an uncalibrated air score. CPU export is provided, but actual Pi speed and Pi-camera accuracy have not been tested. This is not yet a LiteRT export.

The initial grouped check is **exploratory and within a single session**. It is not an independent validation of the final device. There is no liquid-volume measurement in this app. Small/hidden bubbles, different syringes, lighting changes, rotation, or horizontal device geometry can invalidate predictions. Inspect crops before adding labels. The crop detector itself is a framing heuristic, not a learned syringe detector or an out-of-distribution guarantee.

## Files and persistence

`medlock_lab/data/` contains local SQLite labels, original uploads, cleaned images, cached features, weights, and versioned model artifacts. Back up the entire directory to preserve the workspace. This private repository includes data, photographs and models. The virtual environment and temporary caches are excluded from Git. Existing reviewed CSV/XLSX files under `outputs/` remain the initial source; live app changes are in the app database and its own `labels.csv` export.

The `models/<version>/report.json` records the dataset snapshot, preprocessing version, evaluation fold membership and predictions. The active-model pointer is stored transactionally in SQLite.

## Reproduce setup

Use Python 3.11. A conventional fresh environment can install `requirements.txt`. In this workspace `.venv` reuses the computer's existing scientific packages and installs matching torchvision locally.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m medlock_lab seed
.venv/bin/python -m medlock_lab train
.venv/bin/python -m medlock_lab serve
```

Seeding is idempotent and does not overwrite existing human corrections. Use `--manifest /absolute/path/manifest.json` for another reviewed seed manifest. No model or user-supplied pickle file is loaded.

## Tests

```sh
.venv/bin/python -m pytest -q
```

Tests cover preprocessing visibility, corrupt-image rejection, duplicate handling, human-label revisions, persistence, upload/label/train API transitions, concurrent training exclusion, corrections made during training, grouped evaluation separation, and preserving the model after failed training.

Model references: [Torchvision MobileNetV2](https://docs.pytorch.org/vision/0.23/models/generated/torchvision.models.mobilenet_v2.html), [MobileNetV2 paper](https://arxiv.org/abs/1801.04381).

## Raspberry Pi station version

The new [device runtime](medlock_device/README.md) separates deployment from training. It runs the current classifier through an ONNX/OpenCV feature extractor plus its original NumPy logistic-regression head, with replay and real CSI-camera adapters, optional GPIO, a local station interface and event logging. See that guide for the laptop demonstration, deployment bundle, Pi setup and remaining hardware validation.
