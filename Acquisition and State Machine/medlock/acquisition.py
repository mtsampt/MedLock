"""
acquisition.py - MedLock Acquisition Module
Hardware: Raspberry Pi 3 Model B
- Seat detection: EE-SX1070 photo interrupter on GPIO17
  - HIGH (3.3V) = syringe seated (beam blocked)
  - LOW (0V) = not seated (beam unobstructed)
- Backlight: 6x white LEDs via STP36NF06L on GPIO18 (PWM)
- Camera: Raspberry Pi Camera Module
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import time
import logging

logger = logging.getLogger(__name__)

# Lazy imports so module can be imported/tested without hardware
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO not available - running in simulation mode")

try:
    from picamera2 import Picamera2
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    logger.warning("Picamera2 not available - camera disabled")


# --- Hardware Configuration (from report Section 6.2) ---
SEAT_SENSOR_PIN = 17       # GPIO17, input, pull-up on main PCB
BACKLIGHT_PIN = 18         # GPIO18, PWM output
BACKLIGHT_FREQ_HZ = 1000   # 1 kHz PWM (avoid visible flicker)
BACKLIGHT_DUTY = 100       # 100% duty for full illumination

# Timing constants
SEAT_DEBOUNCE_MS = 20      # debounce for mechanical flag insertion
CAMERA_WARMUP_S = 0.5      # let backlight stabilize before capture
CAPTURE_TIMEOUT_S = 5.0


@dataclass
class Measurement:
    volume_ml: Optional[float]
    air_detected: Optional[bool]
    syringe_seated: bool
    valid: bool
    timestamp: str
    error: Optional[str] = None


class Acquisition:
    """Handles sensor reading, image capture, and measurement extraction."""

    def __init__(self, simulate: bool = False):
        self.simulate = simulate or not (GPIO_AVAILABLE and CAMERA_AVAILABLE)
        self._backlight_pwm = None
        self._camera = None
        self._initialized = False

    # ---------- Lifecycle ----------

    def initialize(self):
        """Set up GPIO and camera. Call once at startup."""
        if self._initialized:
            return

        if not self.simulate and GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            # Seat sensor: input. External 10k pull-up on main PCB,
            # but we enable internal pull-up as backup.
            GPIO.setup(SEAT_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            # Backlight MOSFET gate
            GPIO.setup(BACKLIGHT_PIN, GPIO.OUT, initial=GPIO.LOW)
            self._backlight_pwm = GPIO.PWM(BACKLIGHT_PIN, BACKLIGHT_FREQ_HZ)
            self._backlight_pwm.start(0)  # off initially

        if not self.simulate and CAMERA_AVAILABLE:
            self._camera = Picamera2()
            config = self._camera.create_still_configuration()
            self._camera.configure(config)
            self._camera.start()
            time.sleep(1.0)  # sensor warmup

        self._initialized = True
        logger.info("Acquisition initialized (simulate=%s)", self.simulate)

    def shutdown(self):
        """Release hardware resources."""
        if self._backlight_pwm is not None:
            try:
                self._backlight_pwm.stop()
            except Exception:
                pass
            self._backlight_pwm = None

        if self._camera is not None:
            try:
                self._camera.stop()
                self._camera.close()
            except Exception:
                pass
            self._camera = None

        if not self.simulate and GPIO_AVAILABLE:
            try:
                GPIO.cleanup([SEAT_SENSOR_PIN, BACKLIGHT_PIN])
            except Exception:
                pass

        self._initialized = False

    # ---------- Backlight control ----------

    def set_backlight(self, on: bool, duty: Optional[float] = None):
        """Enable/disable backlight. Optional PWM duty 0-100."""
        if self.simulate or self._backlight_pwm is None:
            logger.debug("Backlight -> %s (sim)", on)
            return
        target = duty if duty is not None else BACKLIGHT_DUTY
        self._backlight_pwm.ChangeDutyCycle(target if on else 0)

    # ---------- Seat sensor ----------

    def read_seat_sensor(self) -> bool:
        """
        Read EE-SX1070 photo interrupter.
        Returns True if syringe is seated (beam blocked -> pin HIGH).
        Debounced to reject glitches from mechanical flag insertion.
        """
        if self.simulate:
            return True  # simulation always reports seated

        # Debounce: require N consistent reads
        samples = []
        for _ in range(3):
            samples.append(GPIO.input(SEAT_SENSOR_PIN))
            time.sleep(SEAT_DEBOUNCE_MS / 1000.0)
        # Majority vote
        high_count = sum(1 for s in samples if s == GPIO.HIGH)
        return high_count >= 2

    # ---------- Camera ----------

    def capture_image(self):
        """Capture a still frame with backlight on. Returns image array."""
        if self.simulate or self._camera is None:
            raise NotImplementedError(
                "Camera not connected (simulation mode)"
            )

        self.set_backlight(True)
        time.sleep(CAMERA_WARMUP_S)  # let LEDs stabilize

        try:
            frame = self._camera.capture_array()
            return frame
        finally:
            self.set_backlight(False)

    # ---------- Vision algorithms (stubs to fill in) ----------

    def estimate_volume(self, image) -> Optional[float]:
        """
        Estimate volume in mL from syringe barrel image.

        Approach outline (to be implemented by vision team):
          1. Locate plunger seal and barrel graduations in image.
          2. Map pixel distance to mL using calibration from reference marks.
          3. Return volume, or None if confidence too low.
        """
        raise NotImplementedError("Volume algorithm not implemented")

    def detect_air(self, image) -> Optional[bool]:
        """
        Detect air bubbles/gaps in the fluid column.

        Approach outline:
          1. Segment the fluid column between plunger and needle.
          2. Look for bright (air) regions within the fluid.
          3. Return True if air pocket exceeds threshold size.
        """
        raise NotImplementedError("Air detection not implemented")

    # ---------- Main acquisition ----------

    def acquire(self) -> Measurement:
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            seated = self.read_seat_sensor()

            if not seated:
                return Measurement(
                    volume_ml=None,
                    air_detected=None,
                    syringe_seated=False,
                    valid=False,
                    timestamp=timestamp,
                    error="Syringe not seated",
                )

            image = self.capture_image()
            volume = self.estimate_volume(image)
            air = self.detect_air(image)

            valid = (
                volume is not None
                and volume >= 0
                and air is not None
            )

            return Measurement(
                volume_ml=volume,
                air_detected=air,
                syringe_seated=True,
                valid=valid,
                timestamp=timestamp,
                error=None if valid else "Incomplete measurement",
            )

        except NotImplementedError as exc:
            # Distinguish "not implemented yet" from real faults
            return Measurement(
                volume_ml=None,
                air_detected=None,
                syringe_seated=True,
                valid=False,
                timestamp=timestamp,
                error=f"Not implemented: {exc}",
            )
        except Exception as exc:
            logger.exception("Acquisition failed")
            return Measurement(
                volume_ml=None,
                air_detected=None,
                syringe_seated=False,
                valid=False,
                timestamp=timestamp,
                error=f"Acquisition failed: {exc}",
            )
