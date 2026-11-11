# Independent comparison driver

Source: https://pypi.org/project/XPT2046-asukiaaa-python/1.0.0/
Repository: https://github.com/asukiaaa/XPT2046_asukiaaa_python
Author: Asuki Kono. License: MIT (LICENSE retained).
Wheel SHA256: `27f58842b0cb017e2c60470b6ba9d05a2ee8823f19a7b38f37846529aadecf82`.

`driver.py` is the released source with only its first three hardware imports
replaced by the local `transport` adapter and a provenance comment added.
Command selection, decoding, coordinate range checks, and update logic are
unchanged. This library uses its own response scaling and coordinate range
checks, not MedLock's pressure gate. Counts should not be compared numerically
with the earlier diagnostics as if their scales were identical.

The adapter supplies a minimal SPIDevice context manager and write_readinto
using Linux spidev SPI0.1. Linux drives the confirmed hardware CE1 for each
three-byte transaction. No software GPIO chip-select or IRQ is configured;
this is a transport adaptation, not a separate verification of the Linux SPI
stack or electrical wiring. The test reports raw library commands before
coordinate range filtering. Neither changing numbers nor a non-None coordinate
alone proves reliable touch: hands-off and press responses must separate,
coordinates must respond consistently to position, and releases must work.
