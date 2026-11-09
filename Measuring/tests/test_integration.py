import io
import json
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from medlock_device.runtime import Station, PiCamera, Engine, ReplayCamera
from medlock_device.state_machine import Session, FlowError, load_protocol
from medlock_device.web import create_app


class Camera:
    mode = 'photo replay — test fixture'
    simulated = True
    def capture(self):
        stream = io.BytesIO()
        Image.new('RGB', (600, 800)).save(stream, format='PNG')
        return stream.getvalue(), 'test.png'


class EngineFixture:
    metadata = {'version': 'test'}
    def predict(self, image):
        return {'label': 'no_air', 'air_score': .1}


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.setattr('medlock_device.acquisition.clean', lambda im: (im.resize((224,224)), {'warnings': [], 'stopper_box': [200, 300, 100, 20]}))
    station = Station(EngineFixture(), Camera(), tmp_path/'device.jsonl')
    return Session(station)


def act(flow, action):
    state = flow.snapshot()
    return flow.action(action, state['session_id'], state['revision'])


def ready(flow):
    act(flow, 'begin')
    for _ in flow.protocol['supplies']:
        act(flow, 'confirm')
    for _ in flow.protocol['prep_steps']:
        act(flow, 'next')
    assert flow.snapshot()['screen'] == 'check'


def checked(flow):
    act(flow, 'capture')
    flow.worker.join(timeout=3)
    assert not flow.worker.is_alive()
    return flow.snapshot()


def test_guided_contract_air_only_and_no_completion(flow):
    client = create_app(flow.station, flow).test_client()
    assert client.post('/api/check', json={}).status_code == 409
    ready(flow)
    act(flow, 'seat')
    state = flow.snapshot()
    response = client.post('/api/check', json={'session_id': state['session_id'], 'revision': state['revision']})
    assert response.status_code == 202
    flow.worker.join(3)
    state = client.get('/api/state').get_json()
    assert state['screen'] == 'result'
    result = state['result']
    assert result['air_detected'] is False and result['volume_ml'] is None and result['air_ml'] is None
    assert result['verdict'] == 'unable' and not result['valid']
    assert client.get('/api/preview').status_code == 200
    with pytest.raises(FlowError): act(flow, 'complete')
    assert client.get('/api/supplies').get_json()['holders']['syringe'] == {'present': None, 'correct': None, 'confirmed': True}
    act(flow, 'retry')
    assert flow.snapshot()['result'] is None and client.get('/api/preview').status_code == 404
    assert flow.station.preview is None and not flow.snapshot()['seated']
    assert client.post('/api/capture', json={'seated': True}).status_code == 410


def test_bad_payload_origins_and_stale_actions(flow):
    client = create_app(flow.station, flow).test_client()
    for value in ([], 'bad', None):
        assert client.post('/api/action', json=value).status_code == 400
    state = flow.snapshot()
    payload = dict(action='begin', session_id=state['session_id'], revision=state['revision'])
    assert client.post('/api/action', json=payload, headers={'Origin':'https://other.invalid'}).status_code == 403
    assert client.post('/api/action', json=payload).status_code == 200
    assert client.post('/api/action', json=payload).status_code == 409
    assert client.post('/api/log', json={'event': []}).status_code == 400
    assert client.post('/api/log', json={'event': 'opened_help'}).status_code == 200
    events = [json.loads(line) for line in flow.log_path.read_text().splitlines()]
    assert events[-1]['event'] == 'ui_event' and events[-1]['name'] == 'opened_help'


def test_help_back_reset_and_manual_supplies(flow):
    act(flow, 'begin'); act(flow, 'missing')
    assert flow.snapshot()['missing']
    act(flow, 'help')
    with pytest.raises(FlowError): act(flow, 'confirm')
    act(flow, 'close_help'); act(flow, 'back')
    assert not flow.snapshot()['missing']
    act(flow, 'confirm'); act(flow, 'back')
    assert flow.snapshot()['confirmed'] == []
    act(flow, 'reset'); ready(flow); act(flow, 'back')
    assert flow.snapshot()['prep_index'] == len(flow.protocol['prep_steps']) - 1
    for _ in flow.protocol['prep_steps']: act(flow, 'back')
    assert flow.snapshot()['screen'] == 'supplies'
    assert len(flow.snapshot()['confirmed']) == len(flow.protocol['supplies']) - 1


def test_concurrent_capture_and_reset_discard_late_result(flow):
    ready(flow); act(flow, 'seat')
    entered, release = threading.Event(), threading.Event()
    original = flow.station.camera.capture
    def capture():
        entered.set()
        assert release.wait(3)
        return original()
    flow.station.camera.capture = capture
    act(flow, 'capture')
    assert entered.wait(2)
    with pytest.raises(FlowError): act(flow, 'capture')
    old_worker = flow.worker
    act(flow, 'reset'); ready(flow); act(flow, 'seat')
    with pytest.raises(FlowError): act(flow, 'capture')
    release.set(); old_worker.join(3)
    state = flow.snapshot()
    assert state['screen'] == 'check' and state['result'] is None
    assert checked(flow)['result']['verdict'] == 'unable'


def test_camera_timeout_and_unknown_hardware_seat(flow):
    flow.station.camera = PiCamera()
    flow.station.camera.capture = lambda: pytest.fail('Do not capture without a seat sensor')
    result, _ = flow.station.check(True)
    assert result['syringe_seated'] is None and result['state'] == 'unable'
    flow.station.camera = Camera()
    flow.station.camera.capture = lambda: (_ for _ in ()).throw(subprocess.TimeoutExpired('camera', 20))
    result, _ = flow.station.check(True)
    assert result['syringe_seated'] is True and result['state'] == 'unable'


def test_air_result_survives_unavailable_volume(flow):
    flow.station.volume = SimpleNamespace(estimate=lambda *_: (_ for _ in ()).throw(ValueError('outside calibration')))
    ready(flow); act(flow, 'seat')
    state = checked(flow)
    assert state['result']['air_detected'] is False and state['result']['verdict'] == 'unable'
    assert 'outside calibration' in state['result']['volume_status']


@pytest.mark.parametrize('volume,air,expected', [(1.,False,'pass'),(.8,False,'fix'),(None,False,'unable'),(float('nan'),False,'unable'),(-1,False,'unable'),(1.,True,'fix')])
def test_combined_verdict_rules(flow, volume, air, expected):
    flow.protocol.update(target_volume_ml=1., tolerance_ml=.05)
    result = flow._verdict(dict(state='air_detected' if air else 'no_air_detected', valid=True, syringe_seated=True, air_detected=air, volume_ml=volume))
    assert result['verdict'] == expected


def test_pass_expiry_and_removal_invalidate_completion(flow):
    flow.station.volume = SimpleNamespace(estimate=lambda *_: 1.)
    flow.protocol.update(target_volume_ml=1., tolerance_ml=.05)
    ready(flow); act(flow, 'seat')
    assert checked(flow)['result']['verdict'] == 'pass'
    act(flow, 'help'); act(flow, 'close_help')
    act(flow, 'complete')
    assert flow.snapshot()['screen'] == 'done'
    flow.checked_at -= 61
    assert flow.snapshot()['screen'] == 'check' and flow.snapshot()['result'] is None
    act(flow, 'capture'); flow.worker.join(3)
    flow.station.seat = SimpleNamespace(is_pressed=False)
    assert flow.snapshot()['screen'] == 'check'
    with pytest.raises(FlowError): act(flow, 'complete')


def test_storage_failure_prevents_progress_and_pass(flow, monkeypatch):
    flow.log_path = flow.log_path.parent  # a directory cannot be opened for append
    with pytest.raises(FlowError) as failure: act(flow, 'begin')
    assert failure.value.code == 503 and flow.snapshot()['screen'] == 'start'
    flow.station.log_path = flow.station.log_path.parent
    result, code = flow.station.check(True)
    assert code == 503 and result['state'] == 'unable' and not result['valid']
    assert not flow.station.lock.locked()


def test_invalid_model_and_failed_light_activation_cleanup(flow):
    flow.station.engine.predict = lambda *_: {'label':'no_air', 'air_score': float('nan')}
    assert flow.station.check(True)[0]['state'] == 'unable'
    events=[]
    def on():
        events.append('on')
        raise OSError('partial activation')
    flow.station.light = SimpleNamespace(on=on, off=lambda: events.append('off'))
    assert flow.station.check(True)[0]['state'] == 'unable'
    assert events == ['on', 'off']


def test_real_model_guided_flow_and_log(tmp_path):
    root = Path(__file__).resolve().parents[1]
    station = Station(Engine(root/'outputs/pi-bundle'), ReplayCamera(root/'outputs/medlock-pilot-2026-10-21/images'), tmp_path/'device.jsonl')
    flow = Session(station)
    ready(flow); act(flow, 'seat')
    state = checked(flow)
    assert state['result']['label'] in {'air', 'no_air'}, state
    assert state['result']['verdict'] != 'pass'
    device = json.loads(station.log_path.read_text().splitlines()[-1])
    session = json.loads(flow.log_path.read_text().splitlines()[-1])
    assert device['model_version'] == station.engine.metadata['version']
    assert session['check_id'] == state['check_id'] and session['result']['air_score'] == device['air_score']


@pytest.mark.parametrize('volume', [float('nan'), float('inf'), -1., True])
def test_invalid_volume_adapter_preserves_air_without_emitting_nonfinite_json(flow, volume):
    flow.station.volume = SimpleNamespace(estimate=lambda *_: volume)
    ready(flow); act(flow, 'seat')
    state = checked(flow)
    assert state['result']['verdict'] == 'unable'
    assert state['result']['air_detected'] is False
    assert state['result']['volume_ml'] is None
    json.dumps(state, allow_nan=False)


def test_close_releases_both_gpio_resources_after_light_failure(flow):
    events=[]
    def broken_off():
        events.append('off')
        raise OSError('light failure')
    flow.station.light=SimpleNamespace(off=broken_off,close=lambda:events.append('light closed'))
    flow.station.seat=SimpleNamespace(close=lambda:events.append('seat closed'))
    with pytest.raises(RuntimeError): flow.station.close()
    assert events == ['off','light closed','seat closed']


def test_unseated_check_displays_failure_instead_of_hiding_it(flow):
    ready(flow)
    state=checked(flow)
    assert state['screen']=='result' and state['result']['verdict']=='unable'
    assert state['result']['syringe_seated'] is False


def test_model_bundle_corruption_fails_startup(tmp_path):
    root=Path(__file__).resolve().parents[1]
    metadata=json.loads((root/'outputs/pi-bundle/manifest.json').read_text())
    (tmp_path/'manifest.json').write_text(json.dumps(metadata))
    for name in metadata['sha256']:
        (tmp_path/name).write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='checksum'): Engine(tmp_path)


def test_display_acknowledgement_is_bound_to_current_result(flow):
    ready(flow);act(flow,'seat');state=checked(flow)
    flow.log_client_event('result_displayed',state['check_id'])
    entry=json.loads(flow.log_path.read_text().splitlines()[-1])
    assert entry['check_id']==state['check_id'] and entry['seat_to_display_ack_ms']>=0
    act(flow,'reset')
    with pytest.raises(FlowError):flow.log_client_event('result_displayed',state['check_id'])


@pytest.mark.parametrize('threshold',[float('nan'),float('inf'),True,0,1])
def test_invalid_model_threshold_never_loads(tmp_path,threshold):
    root=Path(__file__).resolve().parents[1]
    metadata=json.loads((root/'outputs/pi-bundle/manifest.json').read_text())
    metadata['threshold']=threshold
    (tmp_path/'manifest.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError,match='threshold'):Engine(tmp_path)


def test_optional_raw_capture_archive_preserves_original_bytes(flow,tmp_path):
    import hashlib
    data,_=flow.station.camera.capture()
    flow.station.capture_dir=tmp_path/'captures';flow.station.capture_dir.mkdir()
    result,_=flow.station.check(True)
    assert Path(result['capture_file']).read_bytes()==data
    assert result['source_sha256']==hashlib.sha256(data).hexdigest()


def test_storage_failure_after_measurement_is_not_presented_as_missing_volume(flow):
    from medlock_device.touchscreen import view
    ready(flow);act(flow,'seat')
    original=flow.station.camera.capture
    def capture():
        flow.log_path=flow.log_path.parent
        return original()
    flow.station.camera.capture=capture
    state=checked(flow)
    assert state['result']['verdict']=='unable' and state['result']['reason_code']=='storage_unavailable'
    assert 'Unable to verify' in view(state)['title']
    assert 'storage' in view(state)['detail']
