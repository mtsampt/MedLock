# Upstream 1.0.0; only the three hardware imports are adapted. See PROVENANCE.md.
from . import transport as spi_device
from .transport import SPI, DigitalInOut
from typing import Optional, Union


class XPT2046(object):
    # Command constants from ILI9341 datasheet
    GET_X = 0b11010000  # X position
    GET_Y = 0b10010000  # Y position
    GET_Z1 = 0b10110000  # Z1 position
    GET_Z2 = 0b11000000  # Z2 position
    GET_TEMP0 = 0b10000000  # Temperature 0
    GET_TEMP1 = 0b11110000  # Temperature 1
    GET_BATTERY = 0b10100000  # Battery monitor
    GET_AUX = 0b11100000  # Auxiliary input to ADC

    coordinate: Optional[tuple[int, int]] = None
    prev_coordinate: Optional[tuple[int, int]] = None
    changed_to_release = False
    changed_to_press = False
    _rx_buf = bytearray(3)
    _tx_buf = bytearray(3)

    def __init__(self, spi: SPI, cs: DigitalInOut,
                 width: int = 240, height: int = 320,
                 x_raw_min: int = 100, x_raw_max: int = 1962,
                 y_raw_min: int = 100, y_raw_max: int = 1900,
                 rotation: int = 0, baudrate: int = 1000000):
        self.spi_device = spi_device.SPIDevice(spi, cs, baudrate=baudrate)
        self.width = width
        self.height = height
        if rotation % 90 != 0:
            raise ValueError("rotation must be multiple of 90")
        self.normalized_rotation = rotation % 360
        # Set calibration
        self.x_raw_min = x_raw_min
        self.x_raw_max = x_raw_max
        self.y_raw_min = y_raw_min
        self.y_raw_max = y_raw_max
        self.x_multiplier = width / (x_raw_max - x_raw_min)
        self.x_add = x_raw_min * -self.x_multiplier
        self.y_multiplier = height / (y_raw_max - y_raw_min)
        self.y_add = y_raw_min * -self.y_multiplier

    def update(self):
        raw = self._read_touch_raw()
        self.prev_coordinate = self.coordinate
        if raw is not None:
            normalized = self._normalize(raw)
            self.coordinate = self._rotate(normalized)
        else:
            self.coordinate = None
        if self.prev_coordinate is None and self.coordinate is not None:
            self.changed_to_press = True
            self.changed_to_release = False
        elif self.prev_coordinate is not None and self.coordinate is None:
            self.changed_to_press = False
            self.changed_to_release = True
        else:
            self.changed_to_press = False
            self.changed_to_release = False

    def is_in_rect(self, rect: tuple[tuple[float, float], tuple[float, float]]) -> bool:
        return is_coodinate_in_rect(self.coordinate, rect)

    def prev_was_in_rect(self, rect: tuple[tuple[float, float], tuple[float, float]]) -> bool:
        return is_coodinate_in_rect(self.prev_coordinate, rect)

    def _normalize(self, pos: tuple[int, int]) -> tuple[int, int]:
        x = int(self.x_multiplier * pos[0] + self.x_add)
        y = int(self.y_multiplier * pos[1] + self.y_add)
        return (x, y)

    def _rotate(self, pos: tuple[int, int]) -> tuple[int, int]:
        (x, y) = pos
        if self.normalized_rotation == 90:
            return (y, x)
        elif self.normalized_rotation == 180:
            return (self.width - x, y)
        elif self.normalized_rotation == 270:
            return (self.height - y, self.width - x)
        else:
            return (x, self.height - y)

    def _read_touch_raw(self) -> Optional[tuple[int, int]]:
        x = self._send_command(self.GET_X)
        y = self._send_command(self.GET_Y)
        if self.x_raw_min <= x <= self.x_raw_max and \
                self.y_raw_min <= y <= self.y_raw_max:
            return (x, y)
        else:
            return None

    def _send_command(self, command):
        self._tx_buf[0] = command
        with self.spi_device as spi:
            spi.write_readinto(self._tx_buf, self._rx_buf)
        return (self._rx_buf[1] << 4) | (self._rx_buf[2] >> 4)


def is_coodinate_in_rect(pos: Optional[tuple[float, float]],
                         rect: tuple[tuple[float, float], tuple[float, float]],
                         #  rect: Union[tuple[float, float, float, float],
                         #              tuple[tuple[float, float], tuple[float, float]]],
                         ) -> bool:
    if pos is None:
        return False
    p_left_up = rect[0]
    p_right_down = rect[1]
    # p_left_up: tuple[float, float]
    # p_right_down: tuple[float, float]
    # if type(rect[0]) in (float, int):
    #     p_left_up = (rect[0], rect[1])
    #     p_right_down = (rect[2], rect[3])
    # else:
    #     p_left_up = rect[0]
    #     p_right_down = rect[1]
    return p_left_up[0] <= pos[0] <= p_right_down[0] and \
        p_left_up[1] <= pos[1] <= p_right_down[1]
