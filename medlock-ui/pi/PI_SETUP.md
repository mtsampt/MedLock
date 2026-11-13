# MedLock on the Raspberry Pi 3B: first test

Goal for day one: the patient UI running on the Pi, doing real camera checks with the team's model, first on an HDMI monitor, then on the 2.8" panel.

Do the parts in order. Each part works on its own, so if one gets stuck you still have the earlier ones to show.

| Part | What it proves | Risk |
|---|---|---|
| A. HDMI + photo replay | Pi runs the UI and the model | Low |
| B. Camera | Real photos go through the model | Low–medium |
| C. 2.8" panel, team's display code | Panel wiring and touch work | Medium |
| D. 2.8" panel, our UI in Chromium | The full patient UI on the real screen | Highest; expect troubleshooting |

---

## 0. On your laptop, before you start

1. Build the UI for the Pi:
   ```sh
   cd ~/Downloads/medlock-ui
   npm run build:pi
   ```
2. Copy these to a USB stick:
   - `~/Downloads/medlock-ui/dist/` and `~/Downloads/medlock-ui/pi/`. Keep them together in a folder named `medlock-ui`.
   - `~/Downloads/MedLock-main/Measuring/outputs/medlock-pi-reference-style/`. Rename the copy to `medlock-station`. This is the only Pi bundle that matches the team's current code. **Don't use `medlock-pi-deployment`; it's outdated.**

## 1. Flash the SD card

In **Raspberry Pi Imager**: Device **Raspberry Pi 3**, OS **Raspberry Pi OS (64-bit)** (the one *with desktop*). Before writing, open the settings (gear / "Edit settings") and set a username and password, your Wi-Fi, and **enable SSH**.

## 2. First boot (HDMI monitor + keyboard, nothing else attached)

Open a terminal and run:

```sh
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-flask python3-numpy python3-pil python3-opencv rpicam-apps
sudo apt install -y chromium || sudo apt install -y chromium-browser
```

Copy the two folders from the USB stick into your home folder, so you have `~/medlock-ui` and `~/medlock-station`.

## A. UI + model, photo replay (HDMI)

```sh
cd ~/medlock-ui
python3 pi/medlock_bridge.py --station ~/medlock-station --replay ~/medlock-station/replay
```

Wait for `MedLock UI: http://127.0.0.1:8768/`. Loading the model takes a while the first time. Then open Chromium at **http://127.0.0.1:8768/** and go through the whole flow.

- Each "Check syringe" uses the next of 3 saved photos: no air, air, air, then it repeats.
- The UI appears as a small 320×240 box on the big monitor. That's expected; zoom with Ctrl + if you like.

**Write down:** seconds from tapping Check to seeing the result, and memory while Chromium is open (`free -h` in a second terminal, "available" column).

Stop the server with Ctrl+C.

## B. Camera

1. **Power off.** Connect the Camera Module 3 Wide to the camera connector between the HDMI and audio ports. Lift the latch, put the ribbon in with the **blue side facing the Ethernet/USB ports**, and press the latch down.
2. Boot and test:
   ```sh
   rpicam-hello --list-cameras     # should list one camera (imx708 wide)
   rpicam-still -o test.jpg        # takes a photo; open it to check
   ```
3. Run the station with the real camera. Drop `--replay`, and add `--rotation 90` or `270` if the photo isn't **plunger at top, tip at bottom**:
   ```sh
   python3 pi/medlock_bridge.py --station ~/medlock-station --rotation 90
   ```

Expect odd results. The model was trained on 27 phone photos, not this camera, so it's a plumbing test, not an accuracy test. "The picture was blurry" or "could not complete the check" means the framing/focus check rejected the photo. Look at the details in `logs/device-events.jsonl`.

## C. 2.8" panel with the team's display code (checks wiring)

The panel is SPI, not HDMI: the Pi doesn't treat it as a monitor until we set that up in part D. Your teammates' code already draws straight to it, so use that first to confirm the wiring.

The panel and knob are already wired on the team's Pi. **Don't rewire.** These are the pins from the team README (BCM numbers):

| Part | GPIO (BCM) | Physical pin |
|---|---|---|
| SPI bus (MOSI / MISO / clock) | 10 / 9 / 11 | 19 / 21 / 23 |
| LCD chip select | 8 (SPI0.0) | 24 |
| LCD D/C | 22 | 15 |
| GPIO18 (startup LCD code claims it; PCB label BACKLIGHT_CTRL) | 18 | 12 |
| Touch chip select | 7 (SPI0.1) | 26 |
| Touch IRQ | not connected | — |
| Seat sensor (HALL_OUT) | 17 | 11 |
| Knob turn A / B | 5 / 6 | 29 / 31 |
| Knob push | 13 | 33 |

The team README says the LCD output works and **touch is not reliable yet**. To see the team's app on the panel, use their command from the team README, section 6 (`scripts/mirror_pi_display.py`).

**Success:** their "Check your syringe" screen appears on the panel and taps work. That means the wiring is right.

## D. Our UI on the 2.8" panel (recorded demo, recommended)

Chromium is too slow on the Pi 3B: a single screenshot of the UI ran for over 16 minutes. So the screens are recorded on the Mac (`pi/record_frames.py`) and the Pi only plays the pictures back on the panel. The knob works just like the real UI. Results come from the mock, not the camera.

On the Mac, after changing the UI: `npm run build && python3 pi/record_frames.py`, then copy `pi/` to the Pi again.

On the Pi:

```sh
cd ~/MedLock/medlock-ui
python3 pi/show_frames.py --take-over --still pi/frames/pass/000.png   # 1. one picture on the panel
python3 pi/show_frames.py --take-over                                  # 2. whole flow with the knob
```

- If turning goes the wrong way, add `--reverse`. If pressing does nothing, try `--button-active-high`.
- `--keys` also lets you drive it from the keyboard in the terminal: `n` next, `p` back, Enter select, `q` quit.
- `--verdict fix` or `--verdict unable` shows the other result screens.
- Ctrl+C stops it and brings the team's home screen back.

## D2. Our UI in Chromium on the 2.8" panel (not workable on a Pi 3B)

This makes the panel act like a normal (tiny) monitor, so Chromium can show the patient UI on it. This part is **untested and the most likely to need fiddling**. If it fights you, stop: parts A–C are already a solid day.

1. Edit `/boot/firmware/config.txt` (`sudo nano /boot/firmware/config.txt`) and add at the end:
   ```
   dtparam=spi=on
   dtoverlay=fbtft,spi0-0,ili9341,dc_pin=22,rotate=90,speed=32000000
   ```
   Check the options with `dtoverlay -h fbtft`. The reset pin isn't listed in the team README; ask the hardware owner. Touch is left out because it isn't reliable yet (no IRQ wired); use the knob or a mouse instead.
   This replaces the team's startup LCD program, so stop it first, and agree this with the team, because the README asks to keep the boot configuration for now.
2. Switch the desktop to X11: `sudo raspi-config` → Advanced Options → Wayland → **X11**.
3. Point the desktop at the panel:
   ```sh
   sudo apt install -y xserver-xorg-video-fbdev
   ls /dev/fb*      # after reboot, the panel is usually /dev/fb1 (fb0 if no HDMI)
   sudo tee /etc/X11/xorg.conf.d/99-spi-panel.conf <<'EOF'
   Section "Device"
     Identifier "SPI panel"
     Driver "fbdev"
     Option "fbdev" "/dev/fb1"
   EndSection
   EOF
   ```
4. Unplug HDMI and reboot. The desktop should appear on the panel. Over SSH, start the bridge as in part A or B, then:
   ```sh
   DISPLAY=:0 chromium --kiosk --force-device-scale-factor=1 --noerrdialogs --disable-infobars http://127.0.0.1:8768/
   ```
   (use `chromium-browser` if `chromium` isn't found).
5. For the knob: `sudo python3 pi/knob.py --a 5 --b 6 --button 13` (add `--reverse` if turning goes the wrong way).

**To undo:** remove the lines from `config.txt` and delete `/etc/X11/xorg.conf.d/99-spi-panel.conf`.

## Results to bring back

- [ ] A: flow works; check takes ___ s; memory available with Chromium open: ___
- [ ] B: camera listed; photo orientation needs rotation ___; checks complete (any result)
- [ ] C: team's screen shows on the panel; touch works
- [ ] D: our UI shows on the panel; touch lands in the right place; feels responsive enough

## Known limits of this test build

- **The pass screen overstates the check.** It says "Ready to inject — Volume and air checks passed", but the camera only checks for visible air; volume isn't measured. Fine on the bench; must change before anyone uses it.
- **Seating is simulated.** No seat sensor is wired, so tapping "Check syringe" counts as "syringe in dock".
- **The server is a prototype.** Flask's built-in server only listens on the Pi itself. Starting automatically at boot comes later.
