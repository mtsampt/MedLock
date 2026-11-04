# SparkFun COM-28379: 320 × 240 touchscreen

The station now defaults to an exact **320 × 240 landscape** interface. It renders with Pillow and bundled DejaVu fonts (license in `fonts/LICENSE_DEJAVU`). The browser displays the same pixels and button rectangles that the native Pi adapter sends to the panel. There is no Chromium requirement for the native path.

## Try it without hardware

Run the existing `python -m medlock_device --bundle ... --replay ...` command and open http://127.0.0.1:8767/.

- **Seat:** tap “Seat (demo)”; no checkbox or tiny controls. The mode label explicitly says PHOTO REPLAY.
- **Capture:** tap “Check syringe”. All controls are disabled during processing; hold-still instructions replace the old result.
- **Result:** text and color distinguish AIR DETECTED, NO AIR DETECTED and UNABLE TO VERIFY. A no-air result is not shown as pass/ready.
- **Details:** a crop thumbnail, timings and short failure advice are on a separate screen.
- **Check again:** returns to the seat/capture screen and clears the displayed result and simulated seat input.

The visual design follows the supplied patient-UI recording: white canvas, blue step progress and primary actions, outlined secondary controls and Help, gray illustration panels, and tinted result cards. Main touch targets are 48 px tall; Help is 60 × 44 px. Main action labels use 14 px bold type. No result screen scrolls. Two bottom actions are kept separate from Help. Help returns to the prior screen and retains its result. The recorded “Ready to inject” claim is not used: this model only checks visible air, and volume remains unimplemented. The desktop diagnostic interface remains at `/desktop`.

## What the display actually needs

SparkFun lists COM-28379 as an **ILI9341 TFT** with an **XPT2046 resistive touchscreen** library, and recommends it for Teensy. It is a component module, not an HDMI monitor or a Raspberry Pi display HAT. Display SPI and touch input are separate interfaces. The Pi adapter is implemented against those controller interfaces, but COM-28379, SPI bus sharing and touch operation are **not hardware tested**.

The native path uses:

- `adafruit-circuitpython-rgb-display` + Blinka for ILI9341 pixel output on Pi SPI0.
- Linux `ads7846` input driver for the XPT2046-compatible touchscreen, exposed as an evdev event device.
- `python-evdev` for ABS_X/ABS_Y/BTN_TOUCH input. Coordinate scaling, swapping and inversion are supported.
- The exact same `TouchUI` state controller, image renderer and inference engine used in browser mode.

Before wiring, agree the pin allocation with the hardware member. Confirm the module supply/backlight requirements against the vendor information; keep Pi GPIO signals within 3.3 V logic. The LCD needs its own CS, DC and RESET pins. The touch controller needs separate CS and IRQ pins. Share SPI clock/data only as supported by the drivers. Do not reuse camera-seat or backlight-control pins for the display. The CLI checks software-controlled pin duplication and SPI0 bus pin conflicts; it cannot verify the physical wiring or the kernel overlay's touch IRQ/CS configuration.

## Pi installation and native launch (after hardware verification)

From the deployment folder, with a system-packages virtual environment already created:

```sh
sudo apt install -y python3-evdev python3-spidev python3-libgpiod
.venv/bin/python -m pip install adafruit-blinka adafruit-circuitpython-rgb-display
```

Enable SPI through Raspberry Pi configuration. Configure the `ads7846` overlay using the **actual touch CS and IRQ wiring**; first read `dtoverlay -h ads7846` on that Pi. Its `penirq` parameter is required. Calibrate axis min/max and orientation, and locate the touch device with `python3 -m evdev.evtest`. Resolve SPI and input-device permissions through the normal `spi`, `gpio` and `input` groups. Do not enable an LCD framebuffer overlay alongside this userspace LCD adapter: only one driver should own the LCD.

The following is a template; replace all angle-bracket values with confirmed wiring/device values:

```sh
.venv/bin/python -m medlock_device --bundle model --replay replay \
  --display ili9341 \
  --display-cs <LCD_CS_BCM> --display-dc <LCD_DC_BCM> \
  --display-reset <LCD_RESET_BCM> \
  --touch-device /dev/input/event<TOUCH_NUMBER>
```

Then omit `--replay replay` to use the camera; set `--rotation 90` or `270` for its mounting as described in README. LCD orientation is independently `--display-rotation 90` (default) or `270`. Calibrate touch to that landscape orientation with `--touch-swap`, `--touch-invert-x`, `--touch-invert-y` as necessary. Do not apply the same correction both in the kernel and the app.

Rendering is event-driven: a full panel frame is sent only when the UI changes. It starts conservatively at 16 MHz SPI and polls touch at 20 Hz; actual bus performance remains unmeasured. Native mode does not start a web server. Its capture worker runs separately, so the checking screen can be drawn while camera/inference work is in progress. Holding a touch produces one action per press.

With no `--seat-pin`, the interface deliberately shows simulated seating even in camera mode. Physical seat GPIO must be configured and validated before that simulation control disappears. No liquid-volume algorithm or injection-clearance decision has been added.

## Acceptance checks when hardware arrives

1. Confirm landscape RGB output, correct rotation and no clipped pixels at all four corners.
2. Calibrate touch; tap every button and all corners. Confirm one action per press and correct release behavior.
3. Check sharing the SPI bus: neither LCD refresh nor touch sampling should select both peripherals at once.
4. Confirm the checking screen remains responsive during a capture; camera timeout/failure returns unable.
5. Test GPIO seat/backlight integration against the finalized wiring and measure total processing latency on the Pi.

## Sources

- [SparkFun COM-28379 product and linked libraries](https://www.sparkfun.com/color-320x240-touchscreen-2-8-inch-ili9341-controller.html)
- [PJRC module documentation](https://www.pjrc.com/store/display_ili9341_touch.html)
- [Adafruit ILI9341/Pillow usage](https://learn.adafruit.com/2-2-tft-display/python-usage)
- [Raspberry Pi ADS7846 overlay parameters](https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README)
- [Python evdev API](https://python-evdev.readthedocs.io/en/latest/apidoc.html)
