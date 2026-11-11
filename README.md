# MedLock

Syringe preparation camera checks and Raspberry Pi station software.

The camera measuring code, photos, datasets, trained models, and deployment artifacts are in [`Measuring/`](Measuring/). Run commands from that folder.

- [Pi: copy-and-paste instructions](#raspberry-pi-copy-and-paste-setup)
- [Project setup and training lab](Measuring/README.md)
- [Pi station setup](Measuring/medlock_device/README.md)
- [320 × 240 touchscreen integration](Measuring/medlock_device/TOUCHSCREEN.md)

The repository includes the collected dataset and a consistent SQLite snapshot. Virtual environments and temporary caches are excluded. The camera model is experimental; volume measurement and physical Pi/display validation remain unfinished.

## Raspberry Pi: copy-and-paste setup

**Open this README in the browser on the Raspberry Pi.** Each code block has a copy button at its top-right. Copy one block, click inside the Pi's Terminal, then **right-click → Paste** and press Enter on the on-screen keyboard. With a physical keyboard, Terminal paste is **Ctrl + Shift + V**. Wait for a block to finish before continuing. If a command reports an error, stop and send the error text or a photo.

These steps run the camera measuring app in `Measuring/`. The separate team patient interface is in `medlock-ui/`; the two are not integrated yet. Keep the existing OS, circuit wiring, and boot display setup.

### 1. Open the project folder and get the latest code

If you already cloned the repository into your home folder, copy this block:

```sh
cd "$HOME/MedLock/Measuring" && git -C .. pull --ff-only
```

If it says the folder does not exist, stop and tell us where you cloned it. If you have **not cloned it yet**, use this block instead:

```sh
cd "$HOME" && git clone https://github.com/mtsampt/MedLock.git && cd MedLock/Measuring
```

### 2. Install the Pi runtime

Copy the entire block. Installation needs internet and may take several minutes. A `sudo` prompt asks for the **Pi login password**; no characters appear as you type it.

```sh
sudo apt update &&
sudo apt install -y python3-venv python3-flask python3-numpy python3-pil python3-opencv python3-gpiozero rpicam-apps &&
python3 -m venv --system-site-packages .venv
```

Use the Pi runtime packages above, not the laptop `requirements.txt`, which also installs the much larger training stack. The Pi uses the committed model and does not need to train it.

### 3. Check the camera

```sh
rpicam-hello --list-cameras
```

Expect a camera entry, normally mentioning `imx708` for Camera Module 3. If it says **No cameras available**, **command not found**, or another error, stop and send that output.

Optionally take a test photo:

```sh
rpicam-still --nopreview --timeout 2000 --output "$HOME/medlock-camera-test.jpg"
```

Open **File Manager → Home → medlock-camera-test.jpg** to inspect it. If the camera is busy, another app may already be using it; report that rather than killing an unknown process.

### 4. First run: test with saved photos

This checks that the model and interface run on the Pi before using the camera:

```sh
.venv/bin/python -m medlock_device --bundle outputs/pi-bundle --replay outputs/medlock-pilot-2026-10-21/images
```

Leave that Terminal open. **In the Pi's browser**, click [Open MedLock on this Pi](http://127.0.0.1:8767/). This address opens the app on whichever computer's browser you use; clicking it on your Mac opens the Mac's app, not the Pi's.

Tap **Seat (demo)**, then **Check syringe**. The first run uses saved photos and simulated seating. The small SPI display is not activated by this command.

### 5. Run with the actual camera

Stop the saved-photo app first. With a physical keyboard, press **Ctrl + C** in its Terminal. With the on-screen keyboard, use its **Ctrl** key and then **C** (release Ctrl afterwards). If that does not stop the app, ask for help before starting another copy.

From the same `Measuring` folder, run:

```sh
.venv/bin/python -m medlock_device --bundle outputs/pi-bundle --rotation 90
```

Refresh [MedLock on this Pi](http://127.0.0.1:8767/) in the Pi's browser. It now captures from the real camera. Seating is still simulated until the seat sensor is configured. Review the cropped image under **Details**.

`--rotation 90` rotates the captured image counterclockwise. Choose `270` for the opposite mounting, or `0` if the image is already upright. The current crop algorithm requires **plunger at the top, tip at the bottom**, with the whole barrel visible. Different lighting and camera geometry can affect predictions; this first run is a hardware/function check, not an accuracy validation.

### 6. Show the app on the little screen (recorded Pi setup)

The recorded `/home/medlock/medlock_home.py` program already drives the LCD using **SPI0.0, GPIO22 (data/command), GPIO18 (screen backlight), 8 MHz SPI, and a 320 × 240 frame**. A bridge now reuses that file's existing `command`, `init_lcd`, and `display_image` functions without modifying it. This matches the recorded code; the new bridge still needs its first physical run.

Copy this whole block into the Pi's Terminal. It updates the code, starts the camera app if necessary, temporarily stops the exact home-screen program, and mirrors the station to the small screen:

```sh
cd "$HOME/MedLock/Measuring" &&
git -C .. pull --ff-only &&
.venv/bin/python scripts/mirror_pi_display.py --start-app --take-over
```

If an earlier Step 4/5 app is already running, the bridge mirrors that existing app (including its current photo-replay/camera mode). If none is running, it starts real-camera mode with image rotation 90. To start with saved photos instead, add `--replay` to the last command. Stop a currently running Terminal app with Ctrl+C first if you want this command to choose a different mode.

**Operate it from the Pi's browser** at [http://127.0.0.1:8767/](http://127.0.0.1:8767/): tap Seat (demo), Check syringe, Details, etc. The same screens should appear on the little LCD. **This enables screen output, not physical touch or rotary-encoder input.** Those still need their input configuration. Seating remains simulated.

Leave the bridge Terminal open. Ctrl+C closes its display resources and restarts the original home-screen script if the bridge stopped it. The original file and boot configuration are unchanged. If the home-screen program automatically respawns or the script reports a GPIO conflict, send the exact error rather than stopping other services.

The bridge checks the recorded constants before taking over and refuses other wiring. It needs `spidev` and `gpiozero`, already used by the working home screen. If Python reports missing `spidev`, install the distro package with `sudo apt install -y python3-spidev` and retry using the system-packages virtual environment from Step 2.

**Pin discrepancy to resolve:** the recorded home-screen script uses GPIO18 for the LCD backlight, while the report also assigns GPIO18 to the imaging backlight driver. Do not configure a second GPIO18 owner with `--light-pin 18` alongside this bridge. Reconcile the actual PCB wiring before separate lighting/sensor integration. The generic ILI9341/Blinka mode in the [touchscreen guide](Measuring/medlock_device/TOUCHSCREEN.md) is a different display owner and must not run at the same time.

### 7. Enable touch on the little screen

First identify the existing touch driver. Open a **second Terminal** so the working screen bridge can stay running, and copy this block:

```sh
cd "$HOME/MedLock/Measuring" &&
git -C .. pull --ff-only &&
python3 scripts/check_pi_touch.py
```

Send a photo of the output. This reports input names, access permissions, SPI driver names and relevant boot overlay settings. It does not read your keystrokes or modify wiring, drivers or boot settings.

**Do not choose a random event device or guess GPIOs.** A keyboard/mouse event device is not the little touchscreen. If the output lists an ADS7846/XPT2046 device, we can enable that device and calibrate it. If no touch controller is configured, we still need its actual touch-CS and IRQ wiring; the LCD's working CS/DC/backlight settings do not identify those touch pins.

The bridge now supports `--touch-device`, `--touch-swap`, `--touch-invert-x` and `--touch-invert-y`. Physical touch remains **unverified** until tested. Its evdev reader uses one action per press, maps coordinates into the same 320 × 240 button regions as the screen renderer, and rejects taps from an old screen revision.

Once a device is confirmed, install `python3-evdev` with apt. Stop/relaunch the bridge and any older station backend so the new revision guard is active. Add the **confirmed** input device to the Step 6 launch command; we will supply that exact copyable command after reviewing the diagnostic output. Touch calibration flags depend on screen orientation. The bridge takes exclusive input ownership while running to prevent touchscreen taps from also clicking the HDMI desktop. Closing it releases that device.

No touch overlay, kernel change, permission-group change or reboot is performed automatically. The setup for a missing ADS7846 driver must use the confirmed touch wiring, not the LCD reset/DC pins. The screen bridge continues to work in display-only mode without these touch arguments.

### Coming back later

Open Terminal and change folders again:

```sh
cd "$HOME/MedLock/Measuring"
```

Then rerun the saved-photo or real-camera command above. Reinstalling packages is not normally needed. For software updates, stop the app and run `git pull --ff-only` from the repository; report any local-change conflict rather than discarding it.
