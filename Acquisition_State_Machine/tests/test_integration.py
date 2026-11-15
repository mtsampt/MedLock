# tests/test_integration.py
import pytest

def test_full_user_cycle(sm, mock_acq):
    """Insert -> measure -> acknowledge -> remove -> IDLE, twice."""
    for cycle in range(2):
        mock_acq.mock_seated = True
        sm.tick()
        assert sm.state is State.SEATED

        mock_acq.mock_volume = 10.0 + cycle
        sm.request_measurement()
        assert sm.state is State.RESULT
        assert sm.last_measurement.volume_ml == 10.0 + cycle

        sm.acknowledge()
        assert sm.state is State.SEATED

        mock_acq.mock_seated = False
        sm.tick()
        assert sm.state is State.IDLE

def test_state_history_recorded(sm, mock_acq):
    """Verify on_state_change fired for every transition."""
    mock_acq.mock_seated = True
    sm.tick()
    mock_acq.mock_seated = False
    sm.tick()
    transitions = [(o.name, n.name) for o, n in sm._test_changes]
    assert ("IDLE", "SEATED") in transitions
    assert ("SEATED", "IDLE") in transitions
