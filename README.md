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
