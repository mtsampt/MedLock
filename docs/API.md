# Unified station API

All routes share the loopback server on port 8767. React assets use the same origin. Hardware never falls back to mock results. The controller owns a single station session shared by all viewers.

- GET /api/state: full session snapshot including protocol, session_id, revision, screen, check_id, result, encoder focus_action and hardware/replay mode.
- POST /api/action: JSON object with action, session_id and integer revision from the latest snapshot. Actions: begin, confirm, missing, next, back, help, close_help, seat (replay only), retry, complete, reset. Stale or forbidden actions return 409. Malformed bodies return 400. Unwritable event storage returns 503.
- POST /api/check: same session_id/revision envelope. Starts capture only from the check screen, returns 202 with checking state immediately. Poll /api/state for result. At most one acquisition runs. Reset invalidates an in-flight check; it does not release the camera to a second check until the original worker exits.
- GET /api/supplies: source=manual confirmation; holder present/correct remain null, confirmed is the user's recorded answer. No supply sensor is implemented.
- POST /api/log: {"event":"name"}, length 1–100. Server timestamps and marks it ui_event. UI-supplied events do not change state or confirm measurements. result_displayed additionally requires the current check_id; it records the server-time interval from seating to receipt of the browser paint acknowledgement. This is an upper-bound timing observation, not a hardware-verified display timestamp. Native output records native_result_displayed after sending the frame.
- GET /api/status: model metadata, session snapshot, volume/air-volume capabilities.
- GET /api/preview: current crop only while the session is on a result screen; otherwise 404.

A check result includes verdict (pass/fix/unable), reason/reason_code, action, nullable volume_ml/air_ml, nullable air_detected, uncalibrated air_score, model_version, calibration_version, syringe_profile, setup_id, source/source_sha256, optional capture_file, timestamp, image_quality, timings (including seat_to_result_ms when available), seat_generation, session_id and check_id. Volume means calibrated occupied barrel volume, not liquid volume calculated by subtracting air. air_ml remains null.

No visible air plus missing volume/configuration yields unable with the available air finding retained. Visible air yields fix. Pass requires valid current acquisition, seating, no detected air, a calibrated finite volume and a configured target/tolerance satisfied by that volume. All results are experimental bench findings, not injection clearance. Completion is prohibited without pass. Results expire after 60 seconds or a detected seating change, and are cleared by retry/back/reset. Sensor polling is not a physical interlock.

POST requests with a foreign Origin are rejected. Use the Vite /api development proxy instead of cross-origin API URLs. The former /api/capture route returns 410 to prevent bypassing the preparation controller.
