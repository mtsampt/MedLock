"""Exercise the actual upload/label/retrain/export loop on an isolated data copy."""
import io
import json
import shutil
import sqlite3
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageEnhance

from medlock_lab.app import create_app
from medlock_lab.imaging import tensor_array
from medlock_lab.model import predict
from medlock_lab.store import Store


def test_real_model_upload_retrain_and_cpu_export(tmp_path):
    root=Path(__file__).resolve().parents[1]/'medlock_lab/data'
    if not (root/'dataset.sqlite3').exists():
        pytest.skip('Initialize the pilot workspace to run the actual-model integration test.')
    data=tmp_path/'data';data.mkdir()
    for folder in ['originals','previews','processed','models','features','weights']:
        shutil.copytree(root/folder,data/folder)
    with sqlite3.connect(root/'dataset.sqlite3') as source, sqlite3.connect(data/'dataset.sqlite3') as target:
        source.backup(target)
    store=Store(data);initial=store.counts()['total'];old_version=store.active_model()['version']
    initial_pending=store.counts()['pending']
    air=next(r for r in store.all() if r['label']=='air')
    # A benign brightness transform is only a functional fixture, not new validation evidence.
    from medlock_lab.imaging import decode
    im=ImageEnhance.Brightness(decode((data/'originals'/air['original_file']).read_bytes())).enhance(.97)
    buffer=io.BytesIO();im.save(buffer,format='JPEG',quality=94)
    app=create_app(data);c=app.test_client()
    result=c.post('/api/upload',data={'image':(io.BytesIO(buffer.getvalue()),'integration-fixture.jpg'),'session':air['session']})
    assert result.status_code==200,result.get_json()
    image=result.get_json()
    assert not image['duplicate'] and image['label'] is None
    assert image['prediction']['label'] in {'air','no_air'}
    assert store.counts()['unlabeled']==1 and store.counts()['pending']==initial_pending
    c.post(f'/api/images/{image["id"]}/label',json={'label':'air'})
    assert store.counts()['pending']==initial_pending+1
    assert c.post('/api/train',json={}).status_code==202
    deadline=time.time()+60
    while time.time()<deadline:
        state=c.get('/api/status').get_json()
        if state['job']['state'] in {'complete','failed'}:break
        time.sleep(.1)
    assert state['job']['state']=='complete',state
    assert state['model']['training_count']==initial+1
    assert state['model']['version']!=old_version
    assert store.counts()['pending']==0
    assert Store(data).active_model()['version']==state['model']['version']
    response=c.get(f'/api/images/{image["id"]}/inspect').get_json()
    assert response['prediction']['seen_in_training']
    import torch
    net=torch.jit.load(str(data/'models'/state['model']['version']/'model_cpu.pt'))
    processed=Image.open(data/'processed'/f'{image["id"]}.png').convert('RGB')
    with torch.inference_mode():
        score=float(net(torch.from_numpy(tensor_array(processed)).unsqueeze(0))[0])
    assert abs(score-response['prediction']['air_score'])<1e-4
    assert c.get('/api/download/model').status_code==200
