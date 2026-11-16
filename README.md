# MedLock

Unified Raspberry Pi bench station: guided preparation UI, shared state machine, camera/GPIO acquisition, existing visible-air model and optional calibrated barrel-volume measurement.

- [Run, package and deploy the unified station](docs/INTEGRATION.md)
- [API and verdict contract](docs/API.md)
- [Integration baseline and display decision](docs/BASELINE.md)
- [Verification status and hardware gates](docs/VERIFICATION.md)
- [Original integration plan](INTEGRATION_PLAN.md)
- [Laptop training lab](Measuring/README.md)

Source folders retain the three contributions: Measuring contains the inference/training packages, medlock-ui contains React, and the root acquisition/state-machine files import the shared implementations in Measuring/medlock_device. There is one acquisition owner and one authoritative controller.

The bundled model detects visible air experimentally. Actual Pi/display/GPIO operation, independent dock accuracy and volume calibration require hardware verification. The default protocol has no target volume/tolerance and cannot issue a combined pass.

## Launch on the small Pi touchscreen

On the Pi, run the command below from your `MedLock` repository folder on the `Code_Together` branch. It reuses the working `main` branch display bridge and `/home/medlock/medlock_home.py` driver: SPI0.0 at 8 MHz, DC GPIO22, LCD backlight GPIO18, and knob GPIO5/6/13. No wiring prompts, reset-pin setting or touch-device configuration are required.

Stop the previous screen bridge, measuring backend and any standalone `knob.py` with Ctrl+C first. The bridge starts the Code_Together guided preparation flow, uses saved syringe photos, and lets you turn the knob to highlight a button and press to select it. It temporarily stops the existing home screen and restores it when you exit with Ctrl+C. The original driver file is read, not edited.

This uses the Pi's existing Measuring virtual environment and display dependencies. The old `python3 Measuring/scripts/launch_touchscreen.py` shortcut now delegates to the same bridge without prompting. The bridge has software checks; this branch's integrated flow still needs a run on your assembled Pi.

```bash
Measuring/.venv/bin/python Measuring/scripts/mirror_pi_display.py --start-app --take-over --replay
```
