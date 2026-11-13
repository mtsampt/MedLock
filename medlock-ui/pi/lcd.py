"""The 2.8" LCD, driven by the team's working startup driver (medlock_home.py).

The driver file is read, never edited; only its display functions are used,
through Measuring/scripts/mirror_pi_display.py in the team repo.
"""
import subprocess
import sys
import time

import numpy as np

WIDTH, HEIGHT = 320, 240


class Lcd:
    """The 2.8" LCD, driven by the team's startup driver functions."""

    def __init__(self, repo, driver, take_over):
        sys.path.insert(0, str(repo / 'Measuring' / 'scripts'))
        import mirror_pi_display as team  # reuse its driver checks and home-screen takeover
        import spidev
        from gpiozero import DigitalOutputDevice

        self.team, self.driver = team, driver
        self.stopped = False
        self.spi = self.dc = self.backlight = None
        code, constants = team.extract_functions(driver.read_text())
        if team.driver_pids(driver):
            if not take_over:
                raise RuntimeError('The home screen is running. Add --take-over to temporarily replace it.')
            self.stopped = team.stop_home(driver)
        self.dc = DigitalOutputDevice(constants['DC_GPIO'], initial_value=False)
        self.backlight = DigitalOutputDevice(constants['BL_GPIO'], initial_value=True)
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 8_000_000
        self.spi.mode = 0
        namespace = {'time': time, 'spi': self.spi, 'dc': self.dc, **constants}
        exec(code, namespace)
        self.command = namespace['command']
        namespace['init_lcd']()

    def show(self, image):
        # Same commands and RGB565 format as the driver's display_image(),
        # converted with NumPy so a frame takes milliseconds instead of seconds.
        rgb = np.asarray(image.convert('RGB'), dtype=np.uint16)
        pixels = ((rgb[..., 0] & 0xF8) << 8) | ((rgb[..., 1] & 0xFC) << 3) | (rgb[..., 2] >> 3)
        data = pixels.astype('>u2').tobytes()
        self.command(0x2A, [0, 0, (WIDTH - 1) >> 8, (WIDTH - 1) & 0xFF])
        self.command(0x2B, [0, 0, (HEIGHT - 1) >> 8, (HEIGHT - 1) & 0xFF])
        self.command(0x2C)
        self.dc.on()
        for i in range(0, len(data), 4096):
            self.spi.writebytes2(data[i:i + 4096])

    def close(self):
        for device in (self.spi, self.dc, self.backlight):
            if device is not None:
                device.close()
        if self.stopped and not self.team.driver_pids(self.driver):
            subprocess.Popen(['/usr/bin/python3', str(self.driver)], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print('Original home-screen program restarted.', flush=True)
