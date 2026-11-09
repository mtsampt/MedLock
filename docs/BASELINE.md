# Integration baseline — November 9, 2026

Source: merge_work at ba09bd6 (main source 3a86592).

- Existing Python suite: **21 passed in 7.24 s**, using Python 3.11.5 and the existing scientific environment on this Mac.
- Existing React production build: **passed**, Vite 5.4.21, 42 modules, about 153 kB JS before gzip.
- Initial npm install reported two dependency advisories; tracked during integration rather than automatically applying a breaking upgrade.
- Source dataset contains null reference_liquid_ml/reference_air_ml values, so it cannot validate volume measurement.
- No Pi, physical GPIO or touchscreen was connected to this checkout during this baseline.

## Display decision

Implement both views against the same backend session: React for a browser-capable display and the native Pillow/ILI9341 path for the documented SPI panel. The native path reuses the guided UI flow and avoids assuming Chromium can drive an unconfigured SPI display. Both paths use the same acquisition owner, protocol and controller; native mode also exposes the same loopback API for diagnostics.

This is a software implementation decision, not a verified hardware selection. Actual panel driver, touch mapping, SPI ownership, memory and performance measurements remain hardware acceptance gates. Use only one LCD driver at a time.
