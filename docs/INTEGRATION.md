# Unified MedLock station

One device process combines the React preparation interface, backend state machine, camera/GPIO acquisition and existing ONNX air model. Native ILI9341 rendering uses the same protocol/session as React. Training remains a separate laptop task.

## Run from source

Build the UI on the laptop with Node.js 22.12 or newer (the Pi needs only the built assets). Use Python 3.11 and the existing scientific environment, or install Measuring/requirements.txt on the laptop, then add Measuring/requirements-device.txt. Build the interface:

```sh
cd medlock-ui
npm ci
npm test
npm run build
cd ../Measuring
python -m medlock_device --replay outputs/medlock-pilot-2026-10-21/images
```

Open http://127.0.0.1:8767/. Begin, confirm each supply manually, advance the prototype preparation steps, tap Seat (demo), then Check syringe. A saved image passes through the actual model. No visible air remains an incomplete combined check until volume is calibrated. Replay is visibly labelled and is not model accuracy evidence. Use Reset or Check again for another attempt.

For UI development run the backend above plus npm run dev in medlock-ui. Vite proxies /api to the local backend. No API URL is required; missing backend configuration never produces a mock pass.

## Build a portable bundle

```sh
cd Measuring
python scripts/package_pi.py
```

The output is deployment/medlock-pi and its .tar.gz in the repository root. Existing output is never overwritten. It contains the device package, minimal preprocessing, built React assets, validated model, three replay images, deployment files and a checksum inventory. It excludes training data, training libraries and the Mac virtual environment. No volume calibration is included.

## Install the bundle on the Pi

Copy the bundle to /opt/medlock. Use a Python 3.11-compatible Raspberry Pi OS 64-bit installation and verify packages for that actual OS. The following is the intended setup; physical Pi installation has not yet been verified:

```sh
sudo apt update
sudo apt install -y python3-venv python3-flask python3-numpy python3-pil python3-opencv python3-gpiozero rpicam-apps
cd /opt/medlock
sha256sum -c FILES.sha256
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-device.txt
.venv/bin/python -m medlock_device --bundle model --replay replay
```

Hardware mode omits --replay and uses --hardware-profile rev0 for the report’s GPIO17 active-HIGH optical seat input with an external pull-up and GPIO18 active-high backlight driver. Confirm the assembled PCB matches the report. For custom wiring, specify --seat-pin, --seat-active high/low and --seat-pull external/up/down explicitly; legacy switches to ground need low/up. Configure --light-pin only for a driver input, never LED power directly. Select --rotation 90 or 270 according to camera mounting. Capture requires the real sensor; there is no always-seated hardware default. Confirm all pins and power requirements before connecting. The camera still uses bounded rpicam-still capture at 1296 × 972 with the original preprocessing/model. The report’s 31 px/mm analysis used the full 4608-pixel sensor width; it does not establish this runtime’s effective resolution or accuracy.

## Display modes

Browser mode (default): serve React on the local port and run Chromium on an OS-managed graphical display. deploy/kiosk.sh waits for backend readiness; install medlock-kiosk.desktop in the graphical user's autostart directory after confirming the OS display driver. No Chromium sandbox is disabled.

Native SPI mode: install the original ILI9341/Blinka and evdev dependencies and configure the touch kernel overlay as described in TOUCHSCREEN.md. Use the confirmed --display ili9341, --display-cs, --display-dc, --display-reset and --touch-device arguments, plus touch orientation settings. The guided flow renders directly at 320 × 240; Chromium is unnecessary. The same local API remains available. Do not run an OS LCD driver alongside the native LCD owner. Actual panel, bus-sharing and touch operation still need hardware verification. See docs/REPORT_ALIGNMENT.md in the source for the report requirements and docs/HARDWARE_ACCEPTANCE.md for the measured test matrix.

## Rotary encoder

The report includes a quadrature rotary encoder with a pushbutton. Pass --encoder-a, --encoder-b and --encoder-switch using confirmed PCB pin numbers; those numbers were not present in the report text. Inputs cannot overlap seat/light/display pins. Rotation highlights available controls, and pressing activates the selected control. With no selection, the first press highlights the primary control. The same selection is shown in React and native output. Queued presses carry a session/revision token, so they cannot activate a control after the screen changes. Physical detent direction, switch polarity/debounce and usability remain bring-up checks.

## Automatic startup

Create a dedicated medlock system user with access to the actual gpio/spi/input/video device groups. Check these groups and device permissions on the chosen OS. Place the immutable application at /opt/medlock, copy deploy/station.env.example to /etc/medlock/station.env, and edit MEDLOCK_ARGS for the chosen display and confirmed wiring. The example explicitly uses replay. Copy deploy/medlock.service to /etc/systemd/system/medlock.service, then run systemctl daemon-reload and systemctl enable --now medlock. Inspect journalctl -u medlock for startup failures. The service creates /var/lib/medlock for logs and permits no application writes elsewhere.

SIGINT/SIGTERM stop the server and join the acquisition worker before GPIO cleanup. The camera subprocess has a 20-second deadline. The service enforces a 45-second stop budget; model/native-driver hangs still need physical fault testing. Reboot/autostart is not yet verified on the Pi.

## Volume calibration

No reference volumes are present in the existing manifest. Collect air-free known fills for the exact syringe, camera resolution/orientation and dock. Use at least two training sessions (six images, three distinct fills) and a separate evaluation session (three images, three fills). Adjacent captures of the same preparation are not independent sessions. Use additional held-out sessions to assess actual device accuracy.

Use --capture-dir /var/lib/medlock/captures during controlled bench trials to retain original camera bytes, with file paths and SHA-256 in check logs. Match each saved capture to its independently measured reference fill; the station never infers a reference label. Prepare CSV columns image,volume_ml,session,split,air_free. split is train or evaluate, air_free is true, paths are relative to CSV. The command rejects duplicate image pixels, mixed resolutions, leakage between session sets, poor focus, unsupported geometry and errors exceeding the specified bound. Example placeholders must be replaced with your agreed experimental criteria:

```sh
python scripts/calibrate_volume.py /path/to/fills.csv --setup-id DOCK_ID --syringe-id SYRINGE_ID --max-error-ml ERROR_BOUND --geometry-margin ALIGNMENT_MARGIN --rotation 90 --output /path/to/calibration.json
```

The algorithm linearly interpolates volume from the fluid-side stopper position; position never extrapolates beyond its calibration envelope. It checks image dimensions, stopper alignment/width and setup ID. It cannot automatically establish syringe identity or detect every lighting/domain change. The operator must use the matching labelled setup. It measures occupied barrel geometry, not air quantity. Synthetic tests verify software behavior only.

Pass --volume-calibration and matching --setup-id to the station. Copy medlock_device/protocol.json to a separate file, set target_volume_ml and tolerance_ml from the agreed bench protocol, and pass --protocol. The runtime requires matching rotation, tolerance at least the calibration error bound and the whole target interval inside the calibrated volume range. Defaults deliberately leave both values null. Hardware calibration and held-out measured error remain pending.

## Verification

Run pytest from Measuring and npm test/npm run build from medlock-ui. See docs/BASELINE.md, docs/API.md and docs/VERIFICATION.md in the source repository for evidence and remaining hardware gates. Tests and replay exercise software integration; they do not establish readiness for patient use.
