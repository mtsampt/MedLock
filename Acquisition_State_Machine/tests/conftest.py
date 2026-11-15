# tests/conftest.py
import pytest
from medlock.acquisition import Acquisition
from medlock.state_machine import StateMachine

@pytest.fixture
def acq():
    """Simulated Acquisition, hardware-free."""
    a = Acquisition(simulate=True)
    a.initialize()
    yield a
    a.shutdown()

@pytest.fixture
def mock_acq():
    """Mock with scriptable seat + measurement results."""
    from medlock.main import MockAcquisition
    a = MockAcquisition()
    a.initialize()
    yield a
    a.shutdown()

@pytest.fixture
def sm(mock_acq):
    """State machine wired to a mock, capturing callbacks."""
    changes = []
    measurements = []
    s = StateMachine(
        mock_acq,
        on_state_change=lambda old, new: changes.append((old, new)),
        on_measurement=measurements.append,
    )
    s._test_changes = changes       # expose for assertions
    s._test_measurements = measurements
    yield s
