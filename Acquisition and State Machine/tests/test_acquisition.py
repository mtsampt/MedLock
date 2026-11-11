# tests/test_acquisition.py
import pytest
from medlock.acquisition import Acquisition, Measurement


class TestReadSeatSensor:
    def test_sim_mode_returns_true(self, acq):
        assert acq.read_seat_sensor() is True


class TestCaptureImage:
    def test_sim_mode_raises_not_implemented(self, acq):
        with pytest.raises(NotImplementedError):
            acq.capture_image()


class TestAcquire:
    def test_not_seated_returns_invalid(self, mock_acq):
        mock_acq.mock_seated = False
        m = mock_acq.acquire()
        assert m.valid is False
        assert m.syringe_seated is False
        assert "not seated" in m.error.lower()

    def test_valid_measurement(self, mock_acq):
        mock_acq.mock_seated = True
        mock_acq.mock_volume = 12.5
        mock_acq.mock_air = False
        m = mock_acq.acquire()
        assert m.valid is True
        assert m.volume_ml == 12.5
        assert m.air_detected is False
        assert m.timestamp.endswith("+00:00")

    def test_negative_volume_rejected(self, mock_acq):
        mock_acq.mock_seated = True
        mock_acq.mock_volume = -1.0
        mock_acq.mock_air = False
        m = mock_acq.acquire()
        assert m.valid is False

    def test_air_detected_still_valid(self, mock_acq):
        mock_acq.mock_seated = True
        mock_acq.mock_volume = 5.0
        mock_acq.mock_air = True
        m = mock_acq.acquire()
        assert m.valid is True
        assert m.air_detected is True

    def test_camera_exception_captured(self, mock_acq):
        mock_acq.mock_seated = True
        mock_acq.raise_on_capture = RuntimeError("boom")
        m = mock_acq.acquire()
        assert m.valid is False
        assert "boom" in m.error
