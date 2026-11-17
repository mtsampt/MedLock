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

## Start automatically when the Pi powers on

On the Pi, stop the existing screen bridge and measuring backend with Ctrl+C. From your `MedLock` folder on `Code_Together`, run this once:

```bash
git pull --ff-only origin Code_Together && python3 deploy/install_pi_startup.py
```

Enter your sudo password if requested. The installer checks the existing Pi environment and model, installs any missing device Python dependencies (including Waitress), and enables the `medlock-screen` system service. It starts the combined flow immediately and on future boots after Raspberry Pi OS starts, without a terminal, desktop login, browser or network connection. Setup may need internet to install missing dependencies. It retains the current saved-photo mode: the images are replayed and the actual model runs when you select Check syringe.

The existing display driver and knob settings are reused. System or user services that directly start `/home/medlock/medlock_home.py` are recorded and disabled so that one program owns the screen. If the installer finds that script in a different startup mechanism, such as a crontab or desktop entry, it reports the location to remove before continuing; it does not edit those files or the driver. If service startup fails, it restores the recorded home-screen services. Backups are kept in `Measuring/runtime/pi-startup-backup.json`. The new startup service reports ready after its first display write succeeds and restarts the combined program if it crashes.

To check it, restart the Pi when convenient and verify that the guided screen and knob work without opening a terminal. Reboot and physical startup verification must be performed on the Pi. Useful commands:

```bash
systemctl status medlock-screen --no-pager
journalctl -u medlock-screen -b --no-pager
sudo systemctl restart medlock-screen
```

To remove this automatic startup and restore the previous home-screen services, run from `MedLock`:

```bash
python3 deploy/install_pi_startup.py --uninstall
```
