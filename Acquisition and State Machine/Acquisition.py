
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Measurement:
    volume_ml: Optional[float]
    air_detected: Optional[bool]
    syringe_seated: bool
    valid: bool
    timestamp: str
    error: Optional[str] = None


class Acquisition:
    """
    Collects measurements and normalizes their format.

    Replace the placeholder methods with real camera/GPIO
    implementations after confirming the hardware interfaces.
    """

    def read_seat_sensor(self) -> bool:
        # TODO
        return True

    def capture_image(self):
        # TODO
        raise NotImplementedError("Camera not connected")

    def estimate_volume(self, image) -> Optional[float]:
        # TODO
        raise NotImplementedError("Volume algorithm not implemented")

    def detect_air(self, image) -> Optional[bool]:
        # TODO
        raise NotImplementedError("Air detection not implemented")

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
                    error="Syringe not seated"
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
                error=None if valid else "Incomplete measurement"
            )

        except Exception as exc:
            return Measurement(
                volume_ml=None,
                air_detected=None,
                syringe_seated=False,
                valid=False,
                timestamp=timestamp,
                error=f"Acquisition failed: {exc}"
            )
