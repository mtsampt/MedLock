# MedLock integrated station

One program that connects the three components:

```
 seat sensor ──► Acquisition ──► StateMachine ──► Controller ──SSE──► React UI (browser / kiosk)
 (GPIO17 or      (MeasuringAcq.   IDLE→SEATED→     ticks 10×/s,       screens switch as the
  simulated)      wraps Station)   MEASURING→       pushes every       machine changes state
                       │           RESULT/ERROR     change
                       └─► Measuring: camera → image check → ONNX air model
```

* **Acquisition + State Machine** decide *what is happening* (syringe in? measuring? result?).
* **Measuring** does the real work when the state machine asks for a measurement.
* **UI** no longer guesses: its syringe-check screens are a function of the machine's state, pushed live.

## Run it

Build the UI once (and again after UI changes):

```sh
cd medlock-ui && npm ci && npm run build:station
```

Then, from the repo root, on the Pi (real camera, simulated seat sensor):

```sh
Measuring/.venv/bin/python -m station
chromium-browser --kiosk --force-device-scale-factor=1 http://127.0.0.1:8770
```

No camera? Replay the saved photos (they cycle, and include air examples):

```sh
Measuring/.venv/bin/python -m station --replay Measuring/outputs/medlock-pilot-2026-10-21/images
```

Real seat sensor on GPIO17 (**confirm polarity first**; see the root README's shared-hardware table):

```sh
Measuring/.venv/bin/python -m station --seat-pin 17                     # LOW when seated
Measuring/.venv/bin/python -m station --seat-pin 17 --seat-active-high  # HIGH when seated
```

Without `--seat-pin` the dock screen shows a **Seat (demo)** button. It disappears when a real seat pin is used.

Developing the UI on a laptop: run the station with `--replay`, then `cd medlock-ui && npm run dev:station`.
Vite proxies `/api` to the station.

## What drives what

| State machine | Dock screen shows | Notes |
| --- | --- | --- |
| `IDLE` | "Dock the syringe", button disabled | removing the syringe at any time returns here |
| `SEATED` | "Syringe detected", **Check syringe** enabled | |
| `MEASURING` | "Checking your syringe…" spinner | camera + air model running |
| `RESULT` | Result screen | air → "Needs a fix"; no air → "No visible air" |
| `ERROR` | Result screen, "Couldn't check" | never shown as a pass |

If a measurement starts or finishes while the patient is on an earlier screen (API call, or a future physical
button), the UI jumps to the check screen. Any trigger works: call `Controller.request_measure()`.

API (local only, `127.0.0.1:8770`): `GET /api/state`, `GET /api/events` (SSE), `POST /api/measure`,
`POST /api/acknowledge`, `POST /api/sim/seat`, `POST /api/log`.

## Tests

```sh
python -m pytest station/tests -q        # controller, HTTP/SSE, and the real model on the pilot photos
cd "Acquisition and State Machine" && python -m pytest -q
```

## Changes to teammates' files (small)

* `Acquisition and State Machine/medlock/state machine.py` is **renamed** `state_machine.py` (the space broke
  `import medlock`), and `from acquisition import` becomes `from .acquisition import`.
* `medlock/acquisition.py`: added `__init__(simulate)`, `initialize()`, `shutdown()` (which `main.py` and the tests
  already called), `Measurement.details`, and `require_volume` so an air-only reading can be valid until volume exists.
* `tests/test_integration.py`: added the missing `State` import.
* `medlock-ui`: new `src/station.js`; `App.jsx`, `SyringeCheck.jsx`, `Result.jsx`, `api.js`, `vite.config.js` and
  `package.json` extended. **Without `--mode station` the UI behaves exactly as before** (mock backend + dev panel).
* `Result.jsx`: when no volume was measured it now says "No visible air · Volume not checked" instead of
  "Ready to inject · Volume and air checks passed", because volume measurement is unfinished.
* `.gitignore`: `node_modules/` and `medlock-ui/dist/`.

## Not done / not verified

* **Not run on the Pi.** Verified here with the real ONNX model on your pilot photos, a real headless browser, and
  simulated seating. The GPIO seat, `rpicam-still`, the light pin and the physical LCD were not exercised.
* **Volume is not implemented.** Hook: `MeasuringAcquisition.estimate_volume(image)` receives the cleaned barrel crop.
* **The SPI LCD still mirrors the old measuring screens**, not this React UI, and physical touch is still unreliable.
  Today the React UI needs a browser window (mouse, or a working touch panel).
* Supplies and prep screens are still patient-tapped, not state-machine-driven.
* Prototype only; results are not clinical validation.

## Measuring test on the little LCD, controlled by knob.py

The measuring LCD bridge can now import the shared control reader from
`medlock-ui/pi/knob.py` directly. **Turn** to move the amber button outline;
**press** to select. No Chromium, virtual keyboard, evdev package, or physical
touch is needed in this mode. Physical knob operation with the measuring app
still needs verification on the assembled Pi; software checks use mocked GPIO.

Stop the earlier screen bridge, standalone `knob.py`, `show_frames.py`, or other
encoder reader with **Ctrl+C** in its own terminal before starting this. One
program must own GPIO5/6/13, and one program must own the LCD. Stop an older
measuring backend too if it reports an old revision.

On the Pi, copy:

```sh
cd "$HOME/MedLock/Measuring" &&
git -C .. pull --ff-only &&
.venv/bin/python scripts/mirror_pi_display.py --start-app --take-over --replay --knob
```

Default pins come from the supplied design: A=BCM5, B=BCM6, push=BCM13. The
first selected button is **Seat (demo)**. Press it to simulate seating, turn
to **Check syringe**, then press again. This command uses saved photos. It
controls the measuring test app on port8767, not the integrated station on
port8770 or the recorded patient UI.

For the **real camera**, stop both the bridge and any separately running
measuring backend, then launch the same command without `--replay`. If a
backend is already running, the bridge keeps its existing replay/camera mode.

If turning feels backward, append `--knob-reverse`. The default push input is
active-low; `--knob-button-active-high` is available if the hardware owner
confirms the opposite polarity. Custom verified pins use `--knob-a`,
`--knob-b`, and `--knob-button`. Ctrl+C releases the knob and LCD resources and
restores the startup display if the bridge stopped it.

**Do not run standalone `knob.py` alongside this command.** Its original
browser-keyboard mode is retained for the patient UI, but the measuring LCD
mode imports its GPIO callbacks directly and runs as one process.

If Git reports a certificate problem, do not disable TLS verification. Check
the Pi's date and the exact browser/Git certificate error. You can run code
already installed without `git pull`, but `--knob` requires this update first.
