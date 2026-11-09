"""Shared acquisition record. Missing capabilities remain explicit."""
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Measurement:
    volume_ml: Optional[float] = None
    air_detected: Optional[bool] = None
    syringe_seated: Optional[bool] = None
    valid: bool = False
    timestamp: str = ''
    error: Optional[str] = None
    state: str = 'unable'
    message: str = ''
    label: Optional[str] = None
    air_score: Optional[float] = None
    air_ml: Optional[float] = None
    volume_status: str = 'not calibrated'
    volume_method: Optional[str] = None
    mode: str = ''
    seat_mode: str = ''
    model_version: str = ''
    calibration_version: Optional[str] = None
    syringe_profile: Optional[str] = None
    setup_id: Optional[str] = None
    source_sha256: Optional[str] = None
    capture_file: Optional[str] = None
    source: str = ''
    session_id: Optional[str] = None
    check_id: Optional[str] = None
    image_quality: dict = field(default_factory=dict)
    inference_ms: Optional[float] = None
    seat_generation: Optional[int] = None
    seat_to_result_ms: Optional[float] = None
    elapsed_ms: float = 0

    def as_dict(self):
        return asdict(self)
    rotation: int = 0
