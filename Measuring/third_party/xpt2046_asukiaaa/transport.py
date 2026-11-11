"""Linux hardware-CS adapter for the upstream CircuitPython SPI interface.

SPI and DigitalInOut names are annotation placeholders; no GPIO is driven.
Each upstream context contains exactly one write_readinto transaction.
"""
SPI = object
DigitalInOut = object


class SPIDevice:
    def __init__(self, spi, cs, baudrate=1_000_000):
        if cs is not None:
            raise ValueError('This adapter uses hardware CE1, not a GPIO CS object.')
        self.spi = spi
        self.baudrate = baudrate

    def __enter__(self):
        self.spi.mode = 0
        self.spi.max_speed_hz = self.baudrate
        return self

    def write_readinto(self, tx, rx):
        rx[:] = bytes(self.spi.xfer2(list(tx)))

    def __exit__(self, *args):
        return False
