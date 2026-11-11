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

The recorded `/home/medlock/medlock_home.py` program already drives the LCD using **SPI0.0, GPIO22 (data/command), GPIO18 (screen backlight), 8 MHz SPI, and a 320 × 240 frame**. A bridge now reuses that file's existing `command`, `init_lcd`, and `display_image` functions without modifying it. The user has confirmed this bridge displays the app on the physical LCD.

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

The supplied **MedLock REV B Gerbers** contain electrical net attributes confirming this wiring:

| Display signal | J2 pad | Pi connection |
| --- | --- | --- |
| T_CS | 11 | BCM GPIO7 / physical pin26 / SPI0.1 |
| T_CLK | 10 | BCM GPIO11 / physical pin23 |
| T_DIN | 12 | BCM GPIO10 / physical pin19 |
| T_DO | 13 | BCM GPIO9 / physical pin21 |
| T_IRQ | 14 | **Unconnected on the PCB** |

The app can **poll the XPT2046 directly over SPI**, checking pressure and position without an IRQ wire. It uses the existing `/dev/spidev0.1`; no wiring change, kernel overlay, evdev package or reboot is needed for this mode. This applies to the supplied REV B layout and matching harness; board revisions or hand modifications require rechecking. Physical touch and calibration remain **unverified until tested on the Pi**.

Stop the currently running bridge with **Ctrl+C**. Also stop any earlier camera backend in its own Terminal so the updated backend can start. Copy this block:

```sh
cd "$HOME/MedLock/Measuring" &&
git -C .. pull --ff-only &&
.venv/bin/python scripts/mirror_pi_display.py --start-app --take-over --spi-touch
```

On first launch, the little screen shows **four blue + targets**, one at a time. Press each center gently for about half a second, then lift. A blunt plastic stylus can help; avoid sharp objects. The fourth point checks the calibration before saving it to `Measuring/outputs/touch-calibration.json`. The app then appears. Try **Help**, **Back**, **Seat (demo)** and **Check syringe**. Seating is still simulated in this launch mode. This controls MedLock on the little screen; it does not add touch to the HDMI desktop.

Later launches reuse calibration. To repeat setup:

```sh
cd "$HOME/MedLock/Measuring" &&
.venv/bin/python scripts/mirror_pi_display.py --start-app --take-over --spi-touch --calibrate-touch
```

If targets do not respond, send the exact terminal output. Do not add an `ads7846` overlay with a guessed IRQ pin: this board leaves that signal unconnected. The polling implementation filters unstable readings, requires consecutive samples and release between actions, and guards against taps on a stale UI revision. Pressure thresholds and responsiveness still need testing on the real controller. Calibration and mocked SPI tests do not establish physical operation.

The alternative `--touch-device /dev/input/eventX` remains available for hardware with a configured Linux touch input driver; it cannot be combined with `--spi-touch`. Its axis flags apply only to that evdev mode. The read-only `python3 scripts/check_pi_touch.py` helper can list input devices and SPI drivers if troubleshooting is needed.

Reference for XPT2046 pressure/position polling and optional IRQ: [PJRC controller implementation](https://github.com/PaulStoffregen/XPT2046_Touchscreen/blob/master/XPT2046_Touchscreen.cpp).

### Coming back later

Open Terminal and change folders again:

```sh
cd "$HOME/MedLock/Measuring"
```

Then rerun the saved-photo or real-camera command above. Reinstalling packages is not normally needed. For software updates, stop the app and run `git pull --ff-only` from the repository; report any local-change conflict rather than discarding it.
