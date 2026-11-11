# MedLock

Shared software and device-testing guide for the MedLock capstone team. Use this README to get code onto the Raspberry Pi and run your component. The components are **not yet one integrated application**.

## Start here: choose your component

| Component | Location | What can run today |
| --- | --- | --- |
| Acquisition | `Acquisition.py` | Python class with placeholder camera, volume, and air methods; no standalone application loop. |
| State machine | `State Machine.py` | Python class for insertion, measuring, result, and error transitions; use the simulated smoke check below. |
| Patient UI | `medlock-ui/` | React browser interface with mock outcomes; can be tested without camera or touch hardware. |
| Measuring / camera | `Measuring/` | Optional saved-photo or real-camera air-classification demo, plus its own browser UI. Volume measurement is unfinished. |
| Little LCD output | `Measuring/scripts/mirror_pi_display.py` | Displays the measuring app on the physical 320 × 240 LCD; demonstrated on this Pi. |
| Physical touch | SPI touch scripts in `Measuring/scripts/` | **Work in progress:** touch readings are not reliable enough for button input. |

- [Pi: copy-and-paste setup](#raspberry-pi-copy-and-paste-setup)
- [Python component testing](#3-test-python-components)
- [Patient UI](#4-run-the-patient-ui-in-the-pis-browser)
- [Optional camera demo](#5-optional-camera-demo)
- [Little LCD output](#6-show-the-app-on-the-little-screen-recorded-pi-setup)
- [Touchscreen — work in progress](#7-enable-touch-on-the-little-screen)
- [Detailed measuring setup and diagnostics](docs/MEASURING_PI.md)

## Raspberry Pi: copy-and-paste setup

Open this README **in the browser on the Pi**. Use each code block's copy button, then right-click inside Terminal → **Paste** → Enter. Physical-keyboard Terminal paste is **Ctrl+Shift+V**. Each block below includes its working folder so it can be pasted from a fresh terminal.

Leave a program's terminal open while using it. **Ctrl+C** stops a foreground program; with the on-screen keyboard, press Ctrl, then C, then release Ctrl. Stop the previous copy before starting another one. If a command fails, keep its output and report it instead of continuing through later commands.

### 1. Get or update the repository

On this device the project lives at `/home/medlock/MedLock`. `$HOME/MedLock` also works if your Pi username differs.

**Already cloned:** stop running tests before pulling updates, then run:

```sh
cd "$HOME/MedLock" &&
git status --short &&
git pull --ff-only
```

If Git reports local edits or a conflict, keep those changes and coordinate with the author. Do not reset or delete a teammate's work to make a pull succeed.

**First clone only:**

```sh
cd "$HOME" &&
git clone https://github.com/mtsampt/MedLock.git &&
cd MedLock
```

### 2. Prepare the shared Python runtime

Run once, or when dependencies change. Installation needs internet. A `sudo` prompt asks for the Pi login password; typed password characters are not displayed.

```sh
sudo apt update &&
sudo apt install -y git python3-venv python3-gpiozero python3-spidev python3-flask python3-numpy python3-pil python3-opencv rpicam-apps &&
cd "$HOME/MedLock" &&
python3 -m venv --system-site-packages Measuring/.venv
```

We reuse **`Measuring/.venv` as the shared Python environment** to stay compatible with the existing device setup. The filename/folder of your code can be elsewhere. Commands call this Python explicitly, so activating the environment is unnecessary. The acquisition/state-machine classes currently need only Python's standard library; GPIO tests additionally need their hardware packages.

Do not install `Measuring/requirements.txt` for basic device testing: it includes the laptop training stack. Install additional component dependencies only when the component owner identifies them. Keep the current OS, boot configuration, and wiring for these tests.

### 3. Test Python components

**Syntax check for the existing team files:**

```sh
cd "$HOME/MedLock" &&
Measuring/.venv/bin/python -m py_compile Acquisition.py "State Machine.py"
```

No output means the syntax check passed. It does not test hardware or prove the code behaves correctly.

**Important current integration issue:** `State Machine.py` imports lowercase `acquisition`, but the committed file is named uppercase `Acquisition.py`. Linux filenames are case-sensitive. Also, both files define classes without an application entry point, so running either file alone will not open a screen or start a continuous sensor test. The component owner still needs to supply the real runner and align the import/filename.

**Optional simulated state-machine smoke check:** this temporary import alias handles the current filename mismatch without renaming or editing team files. It uses a fake acquisition object and does not access the camera, GPIO, or model. The printed volume and air values are fabricated test inputs.

```sh
cd "$HOME/MedLock" &&
Measuring/.venv/bin/python - <<'PY'
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


acquisition = load("acquisition", "Acquisition.py")
state_machine = load("medlock_team_state_machine", "State Machine.py")


class FakeAcquisition:
    seated = False

    def read_seat_sensor(self):
        return self.seated

    def acquire(self):
        return acquisition.Measurement(
            volume_ml=1.0, air_detected=False,
            syringe_seated=True, valid=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


fake = FakeAcquisition()
machine = state_machine.StateMachine(
    fake,
    on_state_change=lambda old, new: print(old.name, "->", new.name),
    on_measurement=lambda reading: print("SIMULATED measurement:", reading),
)
fake.seated = True
machine.tick()
machine.request_measurement()
machine.acknowledge()
fake.seated = False
machine.tick()
machine.shutdown()
assert machine.state is state_machine.State.SHUTDOWN
print("Simulated smoke check finished. No hardware was tested.")
PY
```

Expect `IDLE -> SEATED -> MEASURING -> RESULT`, then acknowledgement returns to `SEATED`, removal returns to `IDLE`, and shutdown reaches `SHUTDOWN`. This covers the simulated happy path only; test error handling and real sensor behavior separately.

For a teammate's **new standalone Python runner**, run it from the repository root using the shared interpreter. Replace the example filename below with the actual runner; this is a template, not an existing file:

```sh
cd "$HOME/MedLock" &&
Measuring/.venv/bin/python "path/to/your_runner.py"
```

Have each component owner document the exact entry point, dependencies, GPIO polarity, and expected output before someone else runs their hardware test.

### 4. Run the patient UI in the Pi's browser

This is the separate React interface in `medlock-ui/`, not the measuring app. Install its runtime once:

```sh
sudo apt update &&
sudo apt install -y nodejs npm &&
node --version &&
npm --version
```

The committed Vite 5 toolchain requires Node 18 or newer. If npm reports an unsupported Node version, resolve that before proceeding.

Start the UI:

```sh
cd "$HOME/MedLock/medlock-ui" &&
npm ci &&
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open [the patient UI on this Pi](http://127.0.0.1:5173/) **in the Pi's browser**. Keep its terminal open. With no `VITE_API_URL` configured, the dev panel lets you choose mock **pass / fix / unable** results and navigate the screens. These results are simulated; they do not come from the sensors or measuring model. No camera or physical touchscreen is required; use the mouse.

If `VITE_API_URL` is set in your environment or local `.env` files, the UI instead tries that backend. The UI expects `GET /supplies`, `POST /check`, and `POST /log`, described in [`medlock-ui/src/api.js`](medlock-ui/src/api.js). The current measuring server at port 8767 has a different API. **Pointing the React UI at 8767 does not integrate them.** No matching standalone FastAPI server is currently committed.

This command displays the UI on the desktop/browser screen. It does **not** send React screens to the little SPI LCD. The existing LCD bridge mirrors only the measuring app's rendered frames. See the [patient UI guide](medlock-ui/README.md) for its own build/preview instructions.

### 5. Optional camera demo

Skip this section if you are testing another component. Stop any program currently capturing from the camera before running either demo.

**Camera-only check — no model or browser needed:**

```sh
rpicam-hello --list-cameras &&
rpicam-still --nopreview --timeout 2000 --output "$HOME/medlock-camera-test.jpg"
```

Expect a camera listing, normally `imx708`, followed by a saved photo at **`/home/medlock/medlock-camera-test.jpg`** on this device. Open it using File Manager → Home. This command captures a still photo and exits; it does not open the MedLock UI or drive the little LCD.

**Optional model demo using the real camera:**

```sh
cd "$HOME/MedLock/Measuring" &&
.venv/bin/python -m medlock_device --bundle outputs/pi-bundle --rotation 90
```

Open [the measuring demo on this Pi](http://127.0.0.1:8767/) in the Pi's browser. Click **Seat (demo)**, then **Check syringe**. Seat status is simulated in this command. It captures a real image and runs the experimental air classifier; it does not measure liquid volume. Check the crop under **Details**. Rotation 90 is the current mounting choice; the crop expects plunger up and tip down.

**No camera available? Use saved photos instead**, after stopping the real-camera demo:

```sh
cd "$HOME/MedLock/Measuring" &&
.venv/bin/python -m medlock_device --bundle outputs/pi-bundle --replay outputs/medlock-pilot-2026-10-21/images
```

Use the same port-8767 browser page. Camera capture, model inference, and GPIO validity are different checks; a successful demo is not a validation of dose or injection readiness.

### 6. Show the app on the little screen (recorded Pi setup)

**LCD output works on the assembled Pi; physical touch does not yet work reliably.** This command shows the measuring app, not the separate React patient UI:

```sh
cd "$HOME/MedLock/Measuring" &&
.venv/bin/python scripts/mirror_pi_display.py --start-app --take-over
```

The bridge reuses `/home/medlock/medlock_home.py`'s display functions without editing that file. It temporarily stops that exact home-screen program and starts the measuring backend if needed. If a backend is already running on 8767, it mirrors that app's existing mode. Otherwise it starts real-camera mode. Add `--replay` to start with saved photos when no backend is running.

Operate the app from the Pi's browser at [127.0.0.1:8767](http://127.0.0.1:8767/) while watching the little LCD. Keep the terminal open. Ctrl+C stops the bridge, releases resources, and restarts the original home-screen script if the bridge stopped it. A separately started backend must be stopped in its own terminal. Do not run another LCD/SPI0.0 writer alongside the bridge.

This bridge expects the recorded startup file and constants: 320 × 240, SPI0.0, D/C GPIO22, and GPIO18 output enabled. It is **not a generic launcher for every teammate's UI**.

### 7. Enable touch on the little screen

**WORK IN PROGRESS — not a working-touch setup. Status: November 11, 2026.** LCD graphics work, but our polling driver and a separate published-driver comparison have not produced reliable two-axis position/pressure readings. Horizontal and vertical movement have both been tried. The cause is unresolved; these tests do not prove a hardware defect.

Use a mouse with the Pi browser for team testing tomorrow. Touch is not a prerequisite for testing acquisition, state-machine logic, or the React mock UI. Do not add `--spi-touch` to the normal LCD launch while trying to test unrelated components: it may stay in calibration until it times out.

The supplied REV B design routes touch CS to **BCM7 / physical pin26**, clock to **BCM11 / pin23**, DIN to **BCM10 / pin19**, and DO to **BCM9 / pin21**. J2 pad14 / T_IRQ is unconnected, so the diagnostic software polls without an IRQ. Actual continuity, controller power/ground, and the touch-panel connection still need checking by the hardware owner.

The calibration commands, diagnostic commands, logs and controller sources are retained in the [detailed measuring/touch guide](docs/MEASURING_PI.md#7-enable-touch-on-the-little-screen). They are troubleshooting tools, not a confirmed repair. Stop any touch reader before running another one. No boot overlay, rewiring, or reboot is required by the current polling test commands.

## Shared hardware: avoid resource conflicts

Use **BCM GPIO numbers in Python**; physical header numbers identify positions on the connector. They are different numbering systems.

| Resource | Design / current software | Testing rule |
| --- | --- | --- |
| CSI camera | Camera Module 3; `rpicam-still` used by measuring | One capture owner at a time. Stop measuring before a teammate's camera capture test. |
| SPI0 bus | GPIO10 MOSI, GPIO9 MISO, GPIO11 clock | LCD and touch share the bus on different chip selects; coordinate ownership and settings. |
| LCD chip select / D/C | GPIO8 (physical24) / GPIO22 (physical15) | One LCD writer at a time; preserve the known working startup driver. |
| Touch chip select | GPIO7 (physical26), SPI0.1 | One touch reader at a time; touch remains WIP. |
| GPIO18 (physical12) | PCB labels it `BACKLIGHT_CTRL`; startup LCD code also claims it | Do not let separate lighting and display programs claim it simultaneously. The LCD module's LED feed is separate in the schematic; the startup variable name does not establish what GPIO18 physically illuminates. |
| Seat input | GPIO17 (physical11), named `HALL_OUT` in the supplied schematic | Confirm assembled sensor type and polarity with hardware owner. The measuring CLI's `--seat-pin` assumes active-low; do not assume that matches this board. Default measuring launches simulate seating. |
| Encoder | GPIO5 / GPIO6 rotation, GPIO13 push | Pin assignments appear in the design; reader/polarity/debounce integration must be supplied and tested by the component owner. |

For hardware pin changes or continuity tests, disconnect power first. Avoid disabling boot services or changing wiring simply to resolve a software conflict; identify the resource owner first.

## Troubleshooting and handing off a test

- **Nothing opens after a Python command:** class-only files may simply exit; a web server prints its URL but still needs the browser opened manually.
- **Page will not load:** keep the server terminal open and use its exact port. Patient UI: 5173. Measuring: 8767. `127.0.0.1` always means the computer running that browser, so open these links on the Pi.
- **Address already in use / old backend revision:** stop the earlier server with Ctrl+C in its own terminal, then restart the updated one. A second launch does not replace an old process.
- **Camera busy / GPIO already claimed:** stop the known program holding it. Do not kill unknown services or launch more copies.
- **Import error for acquisition:** the current uppercase/lowercase mismatch is documented in Step 3. The smoke check's alias is not a permanent integration fix.
- **Module not found:** use `Measuring/.venv/bin/python` and the working folder shown in the command. Ask the component owner for any missing dependency.

For a useful handoff, record: the Git commit (`git rev-parse --short HEAD`), command, simulated versus physical inputs, expected behavior, actual output, and whether you stopped the program. Leave the Pi in a known state and keep diagnostic logs. Internet is needed for Git/package downloads; the local demo pages do not require an internet connection once installed.

## More project documentation

- [Detailed measuring Pi setup and touch diagnostics](docs/MEASURING_PI.md)
- [Measuring project / training lab](Measuring/README.md)
- [Measuring device runtime](Measuring/medlock_device/README.md)
- [Generic display adapter notes](Measuring/medlock_device/TOUCHSCREEN.md) — separate from the proven startup-driver bridge
- [Patient UI](medlock-ui/README.md)

The repository includes local photos, datasets, model files, and a SQLite snapshot. Virtual environments and caches are excluded. All demos remain capstone prototypes; mock results and model outputs are not clinical validation.
