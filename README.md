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

On the Pi, run the command below from your `MedLock` repository folder on the `Code_Together` branch. It launches the native ILI9341 interface using saved syringe photos.

The first run asks for your screen's confirmed CS, DC and RESET BCM pin numbers and full touch input device path. It saves these in `Measuring/runtime/touchscreen.json` and reuses them on later launches. Add `--configure` to enter them again. The launcher uses `Measuring/.venv/bin/python`, the repository's `.venv/bin/python`, or the current Python interpreter, in that order.

The display dependencies, SPI and touch driver must already be configured; see [touchscreen setup](Measuring/medlock_device/TOUCHSCREEN.md). Physical display operation still requires verification on your Pi.

```bash
python3 Measuring/scripts/launch_touchscreen.py
```
