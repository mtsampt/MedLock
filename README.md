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

### 6. Activate the little touchscreen and circuit sensors

The SPI touchscreen needs the **actual LCD CS, DC, RESET pins, touch CS/IRQ configuration, and Linux touch input device**. The seat sensor and backlight also need confirmed pin assignments. The display already showing a MedLock image may have an existing driver or app controlling it.

**Do not guess those pins or start a second display driver.** First identify the current setup with the hardware teammate; then follow [the touchscreen integration guide](Measuring/medlock_device/TOUCHSCREEN.md). The native screen uses the same 320 × 240 renderer as the browser, but needs circuit-specific configuration. Volume measurement remains unimplemented.

### Coming back later

Open Terminal and change folders again:

```sh
cd "$HOME/MedLock/Measuring"
```

Then rerun the saved-photo or real-camera command above. Reinstalling packages is not normally needed. For software updates, stop the app and run `git pull --ff-only` from the repository; report any local-change conflict rather than discarding it.
