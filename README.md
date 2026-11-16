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

On the Pi, start from the repository root: the folder containing `Measuring`, `medlock-ui`, and `deploy`. Replace `/path/to/your/MedLock-repository` with that folder's actual path. The commands below assume the virtual environment is at `Measuring/.venv` and the display dependencies, SPI, and touch driver are already configured; see [touchscreen setup](Measuring/medlock_device/TOUCHSCREEN.md).

Replace `<CS_PIN>`, `<DC_PIN>`, and `<RESET_PIN>` with the ILI9341 screen's confirmed BCM GPIO pin numbers, and `<NUMBER>` with its touch input event number. These placeholders must be replaced before running the command.

```bash
cd /path/to/your/MedLock-repository
git switch Code_Together
cd Measuring

.venv/bin/python -m medlock_device \
  --replay outputs/medlock-pilot-2026-10-21/images \
  --display ili9341 \
  --display-cs <CS_PIN> \
  --display-dc <DC_PIN> \
  --display-reset <RESET_PIN> \
  --touch-device /dev/input/event<NUMBER>
```

This opens the guided interface on the small screen using saved syringe photos. To use the real camera with confirmed Rev0 wiring, replace the `--replay outputs/medlock-pilot-2026-10-21/images` line with `--hardware-profile rev0 --rotation 90`. That profile uses GPIO17 for the seat sensor and GPIO18 for the backlight driver. Use `--rotation 270` instead if required by the camera mounting.
