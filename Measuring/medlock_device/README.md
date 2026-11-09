# MedLock unified device runtime

See [the unified integration guide](../../docs/INTEGRATION.md) for source launch, replay, model packaging, calibration and Pi setup. The React UI and native SPI renderer now share one backend Session controller and Acquisition implementation.

The [touchscreen guide](TOUCHSCREEN.md) retains hardware wiring/driver requirements. Actual camera/GPIO/display behavior and Pi timings remain unverified until physical tests are recorded.

The original visible-air model and preprocessing remain unchanged. Calibration measures occupied barrel volume for one fixed syringe/dock setup; no calibration or target volume is supplied by default.
