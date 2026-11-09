import json
from pathlib import Path
import subprocess
import sys

import pytest
from scripts.package_pi import package


def test_bundle_is_self_contained_offline_and_training_free(tmp_path):
    repo=Path(__file__).resolve().parents[2]
    ui=repo/'medlock-ui/dist'
    if not (ui/'index.html').exists():
        pytest.skip('Run npm ci && npm run build in medlock-ui before packaging tests.')
    out=tmp_path/'station'
    result=package(out,ui)
    assert Path(result['archive']).is_file()
    assert (out/'medlock_device/ui/index.html').is_file()
    assert (out/'deploy/medlock.service').is_file()
    for script in ['record_trial.py','evaluate_trials.py']:
        check=subprocess.run([sys.executable,'-I',str(out/'scripts'/script),'--help'],cwd=tmp_path,capture_output=True,text=True,timeout=10)
        assert check.returncode==0,check.stderr
    assert (out/'docs/BENCH_TRIALS.md').is_file()
    assert not (out/'medlock_lab/model.py').exists()
    script='''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
def no_network(event,args):
    if event == 'socket.connect': raise RuntimeError('Inference must be offline')
sys.addaudithook(no_network)
from medlock_device.runtime import Station,Engine,ReplayCamera
from medlock_device.web import create_app
root=Path(sys.argv[1])
station=Station(Engine(root/'model'),ReplayCamera(root/'replay'),root/'runtime/events.jsonl')
assert create_app(station).test_client().get('/').status_code==200
result,code=station.check(True)
assert code==200 and result['state'] in {'air_detected','no_air_detected'},result
assert not any(name in sys.modules for name in ['torch','torchvision','sklearn'])
print(json.dumps({'state':result['state'],'source':result['source'],'training_libraries_loaded':False}))
'''
    process=subprocess.run([sys.executable,'-I','-c',script,str(out)],cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert process.returncode==0,process.stderr
    assert json.loads(process.stdout)['training_libraries_loaded'] is False
    with pytest.raises(ValueError,match='already exists'):package(out,ui)


def test_packager_rejects_missing_ui_before_creating_output(tmp_path):
    with pytest.raises(ValueError,match='Build medlock-ui'):package(tmp_path/'output',tmp_path/'missing-ui')
    assert not (tmp_path/'output').exists()
