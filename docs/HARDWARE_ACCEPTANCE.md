# Rev0 measured acceptance matrix

Targets are from §3.2–3.4 of the [project report](https://docs.google.com/document/d/1KT73Vt-Gjvi-TdXkccAmyaZ-xqPAkaDDun-uSDHUKAM). All physical criteria below remain **unverified**. Testing uses water and needleless syringes. Keep calibration sessions separate from blinded test sessions.

| ID | Required evidence | Acceptance target | Current software support / remaining work |
|---|---|---|---|
| S1 | Gravimetric reference on a 0.01 g balance; five fills from 0.50 to 2.50 mL, 20 placements each | Error within ±0.05 mL in at least 95% of valid trials | Calibration command, geometry gating, nullable volume and per-check logs implemented. Need actual calibration and 100-placement independent test. |
| S2 | At least 100 randomized preparations with air below, at and above 0.10 mL | Detect at least 0.10 mL air in at least 95% of trials | Binary model integrated. Need labelled controlled-air preparations; score is not air volume. |
| S3 | Blinded combined valid/invalid preparations; record pass, fix and unable separately | Zero false passes; at least 90% passes on valid cases | Default incomplete checks cannot pass; transition/failure tests pass. Combined physical performance is unknown. |
| S4 | 50 load cycles, plus lifted/tilted placements and removal during capture | Detect all 50 loads; lift beyond 1.25 mm reads unseated | Active-HIGH Rev0 adapter, debounce and transition generation implemented. Measure physical margin, polarity and fault behavior. |
| S5 | Seat-to-display timing on the actual Pi, across independent repeated trials | At most 10 seconds in at least 95% of trials | seat_to_result_ms plus result_displayed/native_result_displayed acknowledgement logs implemented. Browser acknowledgement includes transport/paint scheduling; measure actual display timing and Pi memory/cold start. |
| S6 | Ten representative users state the result and next action | At least 9 of 10 understand | Text/symbol/color, help/retry and encoder selection implemented. Need usability sessions, including native display text legibility. |
| S7 | Two unsupported syringe brands in blinded trials | Unable in every trial | Calibration setup/resolution/geometry checks exist. Automatic physical identity is not established; add discrimination if the two-brand test fails. |
| S8 | Actual purchased/fabricated BOM | At most $300 prototype cost | Report budget is planning evidence only; reconcile actual purchases with the hardware team. |

## Bring-up record to complete

Record OS/image version, Pi model, camera part/rotation/focus, image resolution, syringe brand/profile, LCD/touch driver and pin mapping, encoder A/B/switch pins, seat polarity and backlight driver. --hardware-profile rev0 uses report GPIO17 HIGH and GPIO18; verify the assembled wiring before launch.

Confirm supply voltage under load, backlight current/illumination uniformity, GPIO signal levels and input/output permissions. Test sensor disconnection/stuck levels, camera timeout, storage exhaustion and stop/restart cleanup. A pull-up HIGH alone cannot establish sensor health.

For each check save the session/check IDs, reference fill/air quantities, supported/unsupported syringe, expected validity, result/verdict/reason, measured volume, raw air finding, model/calibration versions, image quality and timing. Do not count an unable result as a correct pass or silently exclude it from valid-case yield. Report total trials, denominator and exclusions for each metric.

Finally install the service and chosen display startup, disconnect network access, reboot, repeat the full flow and capture journal/log evidence. Record whether the native SPI or OS/browser path was used; only one driver may own the LCD.
