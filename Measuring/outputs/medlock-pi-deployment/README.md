# MedLock station software for Raspberry Pi 3 Model B

An inference-only station app for SC0022 (Pi 3B, 1 GB) and SC1224 (Camera Module 3 Wide). It reuses the existing fitted model and preprocessing, with a separate deployment path. Nothing here retrains or changes the laptop dataset.

## What you can present now

1. Open the station page. Leave “Simulate syringe seated” unchecked and capture: the result is unable, with no previous prediction retained.
2. Check the box and capture: a saved syringe image goes through the same crop, normalization, ONNX feature extractor and logistic-regression head that the device runtime uses.
3. Show the actual crop, air/no-air result, measured inference time and total processing time.
4. Capture more photos; each event is recorded in JSONL with model version, source, quality and timing.
5. Explain that camera input and GPIO replace the replay adapter and checkbox when the hardware arrives. These hardware paths are written but untested.

A 30-second script:

“I’ve separated the training tool from the software intended to run on the Pi. This version takes a camera image, checks the framing and focus, runs our air detector locally, and displays the result. I can test that flow now by replaying our syringe photos, including failure cases. The exported model is about nine megabytes and doesn’t require PyTorch on the device. Once we have the Pi, I’ll connect the camera and seat sensor, then measure its speed and accuracy.”

Replay includes training images. It demonstrates functionality, not independent model accuracy. Laptop timings are not Pi timings. The blur gate and stopper crop are heuristics, not comprehensive image-quality or full-barrel visibility guarantees. No air result means only “no visible air detected”; there is no overall injection-ready/pass decision or volume estimator.

## Run on this laptop

From the repository root:

```sh
.venv/bin/python -m medlock_device \
  --bundle outputs/pi-bundle \
  --replay outputs/medlock-pilot-2026-10-21/images
```

Open http://127.0.0.1:8767/. This process uses OpenCV, NumPy, Pillow and Flask. It does not import torch, torchvision, scikit-learn, or the training database. It has no inference network requests.

## Re-export after laptop retraining

Install `onnx>=1.16,<1.18` in the laptop environment, then:

```sh
.venv/bin/python scripts/export_pi.py --output outputs/pi-bundle-new
```

The export is fixed-batch FP32 ONNX (opset 12), not quantized. Identity aliases are resolved for OpenCV 4.x compatibility. The exporter compares OpenCV and PyTorch scores on every stored labeled image, requires matching labels and score differences below 0.0001, and deletes its new output if verification fails. It does not overwrite existing bundles. `parity.json` records the check; `manifest.json` records the training snapshot version, input shape, preprocessing version, threshold and file hashes. Runtime validates hashes and preprocessing version on startup.

## Install on the Pi when it arrives

Use a current Raspberry Pi OS 64-bit image. Copy the prepared `outputs/medlock-pi-deployment/` folder to the Pi. Do not copy the laptop virtual environment; it contains Mac binaries. From the copied folder:

```sh
sudo apt update
sudo apt install -y python3-venv python3-flask python3-numpy python3-pil python3-opencv python3-gpiozero rpicam-apps
python3 -m venv --system-site-packages .venv
rpicam-hello --list-cameras
.venv/bin/python -m medlock_device --bundle model --replay replay
```

For a connected monitor, open http://127.0.0.1:8767/ in its browser. From another computer, forward the loopback port over SSH (`ssh -L 8767:127.0.0.1:8767 <pi-user>@<pi-host>`) and open that same local URL. A full desktop/browser may consume much of the 1 GB RAM; SSH viewing avoids that cost.

Replace replay with the actual camera:

```sh
.venv/bin/python -m medlock_device --bundle model --rotation 90
```

Rotation is counterclockwise: choose 90 or 270 to match mounting. The existing model requires **plunger at top, tip at bottom**, centered with the whole barrel visible, even if physically mounted horizontally. Rotation alone does not eliminate the new camera/lighting domain shift. Recollect and label images from the real dock before assessing accuracy.

The camera adapter runs one `rpicam-still` process per capture: 1296×972 JPEG, no preview, autofocus on startup, 1.5-second settling, 20-second subprocess deadline. Then it closes the capture process. This is intentionally single-shot, not continuous video. Capture startup/settling and image processing are included in total timing. Hardware autofocus, focus distance, memory usage and 10-second latency target are all unverified.

GPIO is optional and never enabled automatically. With the hardware member, confirm the actual pin numbers, 3.3 V logic, output polarity and driver circuit. `--seat-pin <BCM>` expects an active-low input to ground with a pull-up; `--light-pin <BCM>` expects an active-high **driver input**, not direct LED power. Replay rejects GPIO options. The runtime checks seating before/after capture and after inference and turns the backlight off after each attempt. This polling is not a continuous movement detector or a hardware interlock. No physical GPIO paths have been tested.

## Next measurements on hardware

- Confirm full-barrel visibility, focus and repeatable crop after removing/replacing the syringe.
- Benchmark cold start, repeated total/inference latency and process RSS on the actual Pi; compare 1 versus 2 inference threads. No real-time performance is claimed yet.
- Fix exposure, lighting, focus distance and camera orientation after finding a repeatable setup; gather independent sessions across bubble sizes/locations and fill levels.
- Evaluate missed-air and false-air counts on those held-out sessions. Retain an unable result for camera, framing or focus failures.
- Implement/calibrate plunger position to occupied volume using this syringe. Binary air detection cannot quantify air or determine liquid volume by subtraction.

## Files and architecture

`runtime.py`: inference engine, replay/CSI camera adapters, serial capture workflow, optional seat/light adapters, append-only event log.
`web.py` + `static/`: local station UI. Flask's development server is a prototype runner; hardened unattended deployment/service setup is future work.
`__main__.py`: CLI; defaults to two OpenCV CPU threads and loopback-only binding.

Model parity is verified on the laptop. Raspberry Pi installation and physical camera/GPIO integration remain unverified until hardware is available.

References: [Pi 3B](https://www.raspberrypi.com/products/raspberry-pi-3-model-b/), [SC1224 part identification](https://www.digikey.com/en/products/detail/raspberry-pi/SC1224/17278644), [official camera software](https://www.raspberrypi.com/documentation/accessories/camera-software.html), [OpenCV DNN](https://docs.opencv.org/4.x/d6/d0f/group__dnn.html).
