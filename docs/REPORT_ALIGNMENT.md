# Alignment with Team 1 Report 2 Fall2026

Source: [project report](https://docs.google.com/document/d/1KT73Vt-Gjvi-TdXkccAmyaZ-xqPAkaDDun-uSDHUKAM), read November 9, 2026. This is implementation context, not evidence that physical tests passed.

## Decisions derived from the report

- §1.4: Rev0 uses water and a single supported 3 mL Luer-lock syringe. Medication identity, injection technique and a physical interlock are outside Rev0. The software keeps the guided preparation flow but labels it a bench prototype; it does not record an injection or invent a dose time.
- §6.1/6.2: Raspberry Pi 3B, GPIO18 backlight MOSFET, GPIO17 optical seat input. The sensor is LOW with the beam clear and HIGH with the syringe seated. --hardware-profile rev0 sets the reported pins/polarity; the SeatSensor uses the PCB's external pull-up. This corrects the original software's active-low assumption.
- §6.3 and BOM: Camera Module 3 Wide and an SPI TFT with rotary encoder/pushbutton. React and native ILI9341 output share one session controller. Encoder pins, LCD control/touch pins and the OS display driver still need the actual schematic/board allocation. No encoder pins have been guessed in the deployment configuration.
- §7.1: one state machine, debounced seat gating, unable on failed seat/image quality. One acquisition owner and one Session now enforce that flow. Seat transitions invalidate a result even after a lift/reseat between controller polls. This is software observation, not a hardware interlock.
- §3.2/3.4: the software exposes check IDs, model versions, quality, capture/inference timing, seating-to-result timing and display acknowledgements to support the specified tests. Those fields do not establish measured performance by themselves.
- §6.6/8: physical assembly/testing is described as future work, targeting November 12 with test data later in November. No hardware results or labelled fill-volume dataset were found in this report.

## Gaps requiring measured evidence

The existing air classifier is binary and uncalibrated as a probability. It has no quantified air-volume output, so the report's ≥0.10 mL air-sensitivity target requires independent controlled-air tests. air_ml remains null.

The new volume estimator interpolates occupied barrel volume from calibrated stopper geometry. It does not subtract air from total volume. Calibration is fixed to a named syringe/dock, resolution, rotation and geometry envelope. Operator profile selection and geometric rejection cannot by themselves prove S7's rejection of every unsupported brand; that requires the two-brand test and possibly additional identification features.

The current rpicam capture uses 1296 × 972, while the report's optical calculation uses 4608 pixels across. Re-evaluate scale, lens distortion and calibration at the actual acquisition resolution. The report's numerical analysis has not been presented as measured model accuracy.

The optical circuit's pull-up can also read HIGH on some wiring/emitter faults; a single digital level cannot diagnose every such failure. Fault injection and any additional sensor-health strategy are hardware acceptance work. The implementation does not claim the zero-false-pass specification has been achieved.

See HARDWARE_ACCEPTANCE.md for the exact S1–S8 acceptance matrix.
