# Integration verification — November 9, 2026

## Story

The guided station UI sends revision-checked actions to the local API; the shared controller runs one acquisition against a saved image, performs actual model inference, logs the result and displays the measured finding. Native SPI rendering uses that same controller.

## Evidence collected

- Baseline: 21 Python tests and the original React build passed before changes.
- Current Python suite: 78 passed (including actual ONNX replay, original training/model regression, acquisition/controller/API tests, volume calibration gates, CLI startup/shutdown/restart). Includes report-aligned seat polarity, transient movement and encoder revision tests. Re-run the current suite to reproduce.
- Frontend: 3 API tests and the production build passed. Build tested with Node 26.7.0, Vite 7.3.8; source requires Node >=22.12.0. Dependency audit reports zero known vulnerabilities after updating the original build tooling.
- Browser, 320 × 240: start -> five manual supply confirmations -> five preparation steps -> simulated seating -> actual replay result. Result displayed **No visible air / Volume not verified**, with no completion button. No browser console warnings/errors were observed. The final replay recorded a [display acknowledgement](evidence/display-ack.json); this is a laptop measurement, not a Pi result.
- Browser refresh retained controller state. Help returned to the same result. Retry cleared the result and simulated seating. An unseated check displayed Unable to verify.
- A check-screen footer overflow was found during viewport testing and corrected. The final [layout readback](evidence/layout.json) showed no main/footer overflow across all five preparation steps and the check screen; all visible buttons fit within x=0..320 and have 44/48 px height.
- Isolated deployment test: built assets and model run from a temporary directory with network connections blocked and no torch/torchvision/sklearn imports.
- Native renderer: generated and visually checked [start](evidence/native-start.png) and [result](evidence/native-result.png) frames from the actual replay controller. This verifies pixels, not SPI hardware.
- Screenshots: [replay result](evidence/replay-result.png), [check screen](evidence/replay-check.png), [unseated result](evidence/unseated-result.png).

## Remaining acceptance gates

The goal is not complete. No physical Pi was connected during these checks. The linked project report has now been read and reconciled in REPORT_ALIGNMENT.md; it describes assembly/testing as upcoming. The following require physical hardware/data:

- Confirm the actual OS, panel driver/touch device, LCD/encoder pin allocation and camera mounting. The report confirms Pi 3B, Camera Module 3 Wide, GPIO17 HIGH=seated and GPIO18 backlight. Verify those signals on the assembled boards.
- Run native or browser output on that actual display, calibrate touch, verify SPI ownership and measure Pi memory.
- Verify real camera framing/focus and seat/light behavior, including movement, timeout and cleanup faults.
- Collect independently labelled air-free known fills; fit and evaluate volume calibration for the actual syringe/dock. Existing reference-volume fields are null. Synthetic calibration tests are not measured volume-accuracy evidence.
- Set the agreed bench target/tolerance only after calibration meets the chosen error bound.
- Install/reboot the Pi service and measure cold start, repeated total/inference latency, memory, offline operation and recovery. The previous 10-second target is unverified.
- Gather independent dock sessions and assess missed-air/false-air performance. Replayed training images prove plumbing only.

Pass remains unavailable in the default configuration. Even a configured/calibrated combined result is an experimental bench result, not injection clearance.
