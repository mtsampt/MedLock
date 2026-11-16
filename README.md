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
