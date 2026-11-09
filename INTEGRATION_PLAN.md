# Raspberry Pi integration plan

Date: November 9, 2026  
Repository: `mtsampt/MedLock`  
Integration branch: `merge_work`  
Starting point: `main` at `3a86592732b867d9f74c1565b48d5c1b78b0dd56`

## Goal and scope

Combine the three contributions into one locally running Raspberry Pi station: the measurement and device code in `Measuring/`, the guided interface in `medlock-ui/`, and the acquisition/controller work in `Acquisition.py` and `State Machine.py`.

This branch initially adds this plan only. All three contributions already exist together on main, so the work is application integration rather than merging three separate Git branches. Preserve the existing training lab and model artifacts while building one device entry point, one controller, and one hardware owner.

The first deliverable is an integrated bench prototype with replay and real-hardware modes. A calibrated volume check is a separate completion requirement for any combined volume-and-air verdict.

## What is implemented today

| Contribution | Reuse | Integration gap |
| --- | --- | --- |
| `Measuring/medlock_device/runtime.py` | ONNX/OpenCV inference, replay and CSI camera adapters, seating checks, backlight cleanup, capture lock, JSONL results | Returns air/no-air/unable, not the React response contract; volume is explicitly unimplemented |
| `Measuring/medlock_device/web.py` | Flask server, status/capture/preview routes and same-origin protection | Routes differ from React; currently serves the older station interface |
| `Measuring/medlock_device/touchscreen.py` and `display_hardware.py` | 320 × 240 native rendering, ILI9341 output and evdev touch | Has its own small interaction controller; native mode does not launch a web server or render React |
| `Measuring/medlock_lab/` and export/package scripts | Training workflow, preprocessing and verified model export | Training dependencies should stay off the deployed Pi; packager does not include React or a shared controller |
| `medlock-ui/` | React/Vite preparation flow, supplies checklist, help and result screens | Uses mocks without an API URL; navigation currently lives in React |
| `Acquisition.py` | `Measurement` record and acquisition skeleton | Seat input always returns true; camera, volume and air methods are placeholders |
| `State Machine.py` | Intended controller location | Empty file: no state-machine implementation to merge |

Important mismatches found in the code:

- React expects `GET /supplies`, `POST /check`, and `POST /log`; Flask currently exposes `/api/status`, `/api/capture`, and related touchscreen routes.
- React expects `volume_ml` and `air_ml`. The current model produces an air classification and an uncalibrated score; it measures neither liquid volume nor air volume.
- `Acquisition.acquire()` calls the unimplemented volume method before air detection, so it cannot currently deliver even an air-only result.
- `Result.jsx` displays “Ready to inject” for a mock pass. An air-only result cannot support that message.
- Supplies are currently confirmed by the user in `Supplies.jsx`; the API holder statuses are mock data, with no implemented supply-identification hardware.
- The documented Pi target is a Pi 3 Model B with 1 GB RAM, Camera Module 3 Wide, and a SparkFun COM-28379 SPI touchscreen. The repository records hardware and performance verification as unfinished.

## Intended architecture

```text
medlock-ui guided screens
         |
local Flask API / shared session state
         |
single station state machine
         |
acquisition orchestration
         |
camera + seat + light adapters -> preprocessing -> air model
                                                   |
                                      future calibrated volume estimator
         |
normalized measurement, verdict and event log
```

Use the existing Flask/device runtime as the starting point. The UI README mentions FastAPI, but no FastAPI backend exists in the inspected code, so introducing a second server is unnecessary.

Keep source folders in place initially. Add importable device modules such as `acquisition.py`, `measurement.py`, and `state_machine.py` under `Measuring/medlock_device/`, migrating the acquisition skeleton into them. Document the replacement for the top-level files rather than maintaining duplicate implementations. Retain `medlock-ui/` as the UI source and `medlock_lab/` as the laptop training tool.

## Implementation sequence

### 1. Establish the integration baseline and display path

- Record the existing Python test results and React production build before modifying behavior.
- Confirm the actual Pi/OS, display wiring/driver, seat and light pins/polarities, camera mounting, and available supply sensors with the team.
- Test the React UI on the actual 320 × 240 display early. A Chromium kiosk needs a working OS display/framebuffer or compositor path for this SPI panel; the existing Python ILI9341 adapter does not provide that.
- Prefer serving the built React UI in a local kiosk if the display driver and Pi memory budget support it. If they do not, reuse the React flow, content and visual design in the native Pillow renderer, driven by the same backend controller. Record this decision before building the full UI integration.
- Keep one owner for the display, touch input and each GPIO resource. Do not run native display output alongside an OS driver that also owns the LCD.

Acceptance: reproducible baseline recorded and a demonstrated display path selected, or the exact hardware dependency documented.

### 2. Define the shared measurement and API contract

- Extend the existing measurement record to distinguish seating, image quality, air classification, measured volume, validity, errors and timestamp. Include a check/session identifier, model version and explicit replay/hardware mode.
- Keep independent capabilities explicit. An unavailable volume estimate must not prevent air detection from running, and must not produce a valid combined measurement.
- Retain `volume_ml: null` until an estimator exists. Keep `air_ml: null` unless air volume is actually measured. Store the existing air score separately.
- Implement the UI endpoints on the existing Flask application, using one documented API prefix consistently, for example `/api/supplies`, `/api/check`, and `/api/log`. Update `src/api.js` at the same time.
- Add session/state reads and action endpoints for preparation progress. Return structured busy, timeout, invalid-action and unavailable responses.
- Identify supplies as manual confirmation, simulated status, or actual sensor evidence. Unknown hardware status must not masquerade as a detected, correct item.

Acceptance: example requests/responses and verdict rules agreed in code/docs, with tests for absent capabilities and malformed data.

### 3. Connect acquisition to the existing hardware and model code

- Reuse `PiCamera`, `ReplayCamera`, `Engine`, and the existing preprocessing instead of opening a second camera or recreating inference.
- Refactor `Station.check()` and `Acquisition.acquire()` into one acquisition path, preserving capture serialization, orientation handling, quality checks, repeated seat checks, light cleanup and model validation.
- Inject adapters so replay, hardware failures and movement can be tested without a Pi. Require explicit simulated inputs in replay mode; remove the always-true seat default from hardware mode.
- Clear stale results before every check. Reject overlapping checks and prevent a completed worker from updating a cancelled or restarted session.
- Preserve useful evidence when a later operation fails; report unknown seating separately from a confirmed unseated syringe.
- Make timeouts and shutdown release camera, light and GPIO resources reliably.

Acceptance: replay image -> normalized air result works through the API; camera, framing, seating and model failures return unable without leaving outputs active.

### 4. Implement the shared state machine

- Build the missing controller for start -> supplies -> preparation steps -> syringe placement -> checking -> result -> completion, with retry, back, help and reset actions.
- Let the backend own the session state and allowed transitions. React and any native renderer display that state and submit actions.
- Track result freshness. Removal, retry, reset or relevant preparation changes invalidate the prior check. Completion requires the current session's eligible result.
- Reject invalid transitions and duplicate check requests. Keep help available without accidentally advancing the flow; define behavior for refresh, restart and an interrupted check.
- On restart, begin in a known state and require a new check rather than restoring a previously displayed pass.

Acceptance: transition tests cover normal progress, retry, help, reset, in-flight requests and stale results.

### 5. Replace UI mocks with the real flow

- Update `api.js` to check HTTP status and response shape and to time out requests. Make simulation an explicit development setting rather than silently falling back to mock passes when configuration is missing.
- Serve the React production assets and API from the same local origin. Configure a development proxy as needed while preserving the backend's origin checks.
- Connect preparation actions, checking progress and results to the shared controller; remove competing navigation logic.
- Until volume exists, show “No visible air detected; volume not checked” and keep the combined pass/completion path unavailable. Air detected can request correction; incomplete or failed checks remain unable.
- Revise the “Ready to inject” claim and prototype copy to match what is actually measured. Keep medication steps and target volume explicitly configured as prototype content.
- Verify help, retry, disconnect and error screens at 320 × 240, including long messages and touch targets. If native rendering was selected in step 1, implement these same states in that renderer.

Acceptance: the full guided bench flow runs against real backend/replay results with no hidden mocks, false volume values or unsupported completion.

### 6. Add and calibrate volume measurement

- Implement plunger-position/geometry measurement for the actual syringe and dock, using labelled images with known fill amounts and repeated seating.
- Define supported syringe types, camera geometry, calibration units, acceptable error and out-of-range behavior before enabling a volume verdict.
- Keep volume estimation independent from the existing binary air model. Air classification cannot supply an air volume to subtract.
- Configure the target and tolerance centrally and expose the same values to the UI. Do not invent a production tolerance from the UI's placeholder 1.0 mL target.
- Permit a combined prototype pass only when seating, image quality, volume capability, configured tolerance and air checks are all satisfied for the current check.

Acceptance: measured error reported on held-out dock images; missing calibration, unsupported geometry or missing measurements prevent combined pass.

### 7. Package and verify one Pi application

- Extend `package_pi.py` to include the integrated Python modules, built UI or selected native renderer, model bundle, configuration and launch documentation.
- Separate device dependencies from laptop training dependencies. Keep PyTorch, torchvision and scikit-learn out of the inference deployment.
- Provide one launch command with explicit replay/hardware selection, model path, GPIO/display settings and writable log location. Preserve checksum/preprocessing validation.
- Add service and display startup configuration for the selected display path, with controlled restart, orderly shutdown and clear startup failures.
- Test a fresh Pi installation, offline startup, reboot and repeated sessions. Record camera/inference/total latency and memory use on the actual Pi; evaluate the existing 10-second target rather than assuming it is met.
- Preserve the existing training dataset and model history. Keep replay test images and simulated verdicts clearly identified.

Acceptance: a documented deployment bundle starts the unified station after reboot and completes repeated checks without manual development-server steps.

## Verification before calling the integration complete

- Existing preprocessing, model parity, lab and device tests still pass.
- Contract/controller tests cover air detected, no visible air, absent volume, volume out of tolerance, invalid numbers, movement, poor image quality, camera timeout, missing/corrupt model, concurrent checks, refresh/reset, stale responses and storage failures.
- End-to-end replay verifies UI -> API -> controller -> acquisition -> model -> displayed result and event log.
- Hardware checks verify camera framing/focus, seat polarity/debounce, light cleanup, touch calibration, display rendering and reboot recovery.
- Accuracy evaluation uses separately collected dock sessions; training-image replay is a functional demo, not independent accuracy evidence.
- No combined pass is emitted until volume measurement and its required checks are implemented and evaluated.

## Suggested commit milestones

1. Baseline notes, display decision and shared contract.
2. Acquisition integration and adapter tests.
3. Shared state machine and API.
4. Connected guided UI and end-to-end replay.
5. Volume estimator and calibration evidence.
6. Pi packaging, startup and hardware verification results.

The first useful milestone is the guided interface running an actual replay check through the shared controller. The final integrated Pi milestone additionally requires the real display/camera/GPIO path and measured hardware results. A complete volume-and-air verdict remains dependent on the volume work described above.
