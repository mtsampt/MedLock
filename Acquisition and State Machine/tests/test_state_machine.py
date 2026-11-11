# tests/test_state_machine.py
from medlock.state_machine import State, Event

class TestTransitions:
    def test_boot_in_idle(self, sm):
        assert sm.state is State.IDLE

    def test_insert_moves_to_seated(self, sm, mock_acq):
        mock_acq.mock_seated = True
        sm.tick()
        assert sm.state is State.SEATED

    def test_remove_returns_to_idle(self, sm, mock_acq):
        mock_acq.mock_seated = True
        sm.tick()
        mock_acq.mock_seated = False
        sm.tick()
        assert sm.state is State.IDLE

    def test_measure_requires_request(self, sm, mock_acq):
        mock_acq.mock_seated = True
        sm.tick()
        assert sm.state is State.SEATED
        # No request -> still seated
        assert sm.state is State.SEATED

    def test_measure_from_seated(self, sm, mock_acq):
        mock_acq.mock_seated = True
        mock_acq.mock_volume = 10.0
        sm.tick()
        sm.request_measurement()
        assert sm.state is State.RESULT

    def test_measure_when_idle_does_nothing(self, sm):
        sm.request_measurement()
        assert sm.state is State.IDLE

    def test_acknowledge_from_result(self, sm, mock_acq):
        mock_acq.mock_seated = True
        sm.tick()
        sm.request_measurement()
        sm.acknowledge()
        assert sm.state is State.SEATED

    def test_shutdown_is_terminal(self, sm):
        sm.shutdown()
        assert sm.state is State.SHUTDOWN
        sm.tick()              # should be a no-op
        assert sm.state is State.SHUTDOWN

    def test_removal_during_result_returns_idle(self, sm, mock_acq):
        mock_acq.mock_seated = True
        sm.tick()
        sm.request_measurement()
        assert sm.state is State.RESULT
        mock_acq.mock_seated = False
        sm.tick()
        assert sm.state is State.IDLE

    def test_invalid_measurement_lands_in_error(self, sm, mock_acq):
        mock_acq.mock_seated = True
        mock_acq.mock_volume = None
        sm.tick()
        sm.request_measurement()
        assert sm.state is State.ERROR
