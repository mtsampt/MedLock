import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from medlock_device.runtime import Engine, PiCamera, ReplayCamera, Station
from medlock_device.web import create_app
from medlock_lab.imaging import ImageProblem


class FakeEngine:
    metadata = {'version': 'test', 'threshold': .5, 'training_count': 27}
    def predict(self, im):
        return {'label': 'no_air', 'air_score': .1}


class FakeCamera:
    mode = 'test camera'
    def capture(self):
        stream = io.BytesIO()
        Image.new('RGB', (600, 800)).save(stream, format='PNG')
        return stream.getvalue(), 'test.png'


@pytest.fixture
def station(tmp_path, monkeypatch):
    monkeypatch.setattr('medlock_device.runtime.clean', lambda im: (im.resize((224,224)), {'warnings': []}))
    return Station(FakeEngine(), FakeCamera(), tmp_path/'log.jsonl')


def test_result_then_unseat_clears_prediction_and_preview(station):
    client=create_app(station).test_client()
    assert client.post('/api/capture', json={'seated': True}).get_json()['state']=='no_air_detected'
    assert client.get('/api/preview').status_code==200
    r=client.post('/api/capture', json={'seated': False}).get_json()
    assert r['state']=='unable' and r['label'] is None and r['air_score'] is None
    assert client.get('/api/preview').status_code==404
    assert r['volume_ml'] is None
    lines=[json.loads(line) for line in station.log_path.read_text().splitlines()]
    assert len(lines)==2 and lines[-1]['label'] is None


def test_string_true_is_not_seated(station):
    assert create_app(station).test_client().post('/api/capture',json={'seated':'true'}).get_json()['state']=='unable'


def test_failure_turns_off_backlight_and_can_retry(station):
    events=[]
    station.light=SimpleNamespace(on=lambda:events.append('on'),off=lambda:events.append('off'))
    station.camera.capture=lambda: (_ for _ in ()).throw(subprocess.TimeoutExpired('camera',20))
    r,_=station.check(True)
    assert r['state']=='unable' and r['air_score'] is None
    assert events==['on','off'] and not station.lock.locked()
    station.camera=FakeCamera()
    assert station.check(True)[0]['state']=='no_air_detected'


def test_quality_failure_does_not_call_classifier(station,monkeypatch):
    monkeypatch.setattr('medlock_device.runtime.clean',lambda im:(im,{'warnings':['blur']}))
    station.engine.predict=lambda im: pytest.fail('Do not infer on a rejected image')
    assert station.check(True)[0]['state']=='unable'


def test_seat_moves_during_capture(station):
    class Seat:
        reads=0
        @property
        def is_pressed(self):
            self.reads+=1
            return self.reads==1
    station.seat=Seat()
    assert station.check(True)[0]['state']=='unable'


def test_busy_and_cross_origin(station):
    station.lock.acquire()
    try:
        assert station.check(True)[1]==409
    finally:
        station.lock.release()
    assert create_app(station).test_client().post('/api/capture',json={'seated':True},headers={'Origin':'https://example.com'}).status_code==403


def test_real_camera_command_has_deadline_and_no_shell(monkeypatch):
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(stdout=b'jpeg')
    monkeypatch.setattr('medlock_device.runtime.subprocess.run',run)
    assert PiCamera().capture()[0]==b'jpeg'
    args,kw=calls[0]
    assert args[0]=='rpicam-still' and kw['timeout']==20 and kw['check']
    assert '--autofocus-mode' in args and 'shell' not in kw


def test_replay_cycles_without_altering_originals(tmp_path):
    for name in ['002.JPG','001.JPG']:
        (tmp_path/name).write_bytes(name.encode())
    cam=ReplayCamera(tmp_path)
    assert [cam.capture()[1] for _ in range(3)]==['001.JPG','002.JPG','001.JPG']


def test_actual_onnx_runtime_and_failed_image(tmp_path):
    root=Path(__file__).resolve().parents[1]
    bundle=root/'outputs/pi-bundle'
    photos=root/'outputs/medlock-pilot-2026-10-21/images'
    if not bundle.exists() or not photos.exists():
        pytest.skip('Export bundle and seed images to run actual-model device check.')
    station=Station(Engine(bundle),ReplayCamera(photos),tmp_path/'events.jsonl')
    result,_=station.check(True)
    assert result['state'] in {'air_detected','no_air_detected'},result
    assert 0<=result['air_score']<=1
    station.camera.capture=lambda:(b'corrupt','broken.jpg')
    assert station.check(True)[0]['state']=='unable'
    assert station.preview is None
