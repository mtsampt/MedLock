import io
import json
import threading
import time

import numpy as np
import pytest
from PIL import Image, ImageDraw

from medlock_lab.app import create_app
from medlock_lab.imaging import ImageProblem, clean, decode
from medlock_lab.model import evaluate
from medlock_lab.store import Store


def photo(bubble=False, shift=0):
    im=Image.new('RGB',(600,800),(215+shift,213,195))
    d=ImageDraw.Draw(im)
    d.rectangle((260,170,340,670),outline=(140,140,130),width=2)
    d.rectangle((260,380,340,415),fill=(35,35,35))
    if bubble: d.ellipse((275,445,325,495),outline=(75,85,75),width=3)
    b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()


def trained_store(path):
    s=Store(path)
    a,_=s.add(photo(True),'air.png','s1',label='air')
    b,_=s.add(photo(False),'no.png','s1',label='no_air')
    s.activate({'version':'test-v1','training_count':2,'snapshot':{r['id']:r['revision'] for r in s.all()},'evaluation':{'available':False},'trained_at':'2026-10-21T12:00:00+00:00'})
    return s,a,b


def test_preprocessing_preserves_air_region_and_rejects_non_photo():
    out,meta=clean(decode(photo(True)))
    assert out.size==(224,224)
    l,t,r,b=meta['crop_box']
    assert l<275 and r>325 and t<445 and b>495
    with pytest.raises(ImageProblem): decode(b'not an image')
    with pytest.raises(ImageProblem): clean(Image.new('RGB',(600,800),'white'))


def test_duplicate_manual_labels_and_revision_tracking(tmp_path):
    s,a,b=trained_store(tmp_path)
    _,duplicate=s.add(photo(True),'different-name.png','s2')
    assert duplicate and len(s.all())==2
    assert s.counts()['pending']==0
    s.label(a['id'],'air')
    assert s.counts()['pending']==0
    s.label(a['id'],'no_air')
    assert s.counts()['pending']==1
    fresh,_=s.add(photo(True,shift=2),'new.png','s2')
    assert fresh['label'] is None and s.counts()['pending']==1
    s.label(fresh['id'],'air')
    assert s.counts()['pending']==2
    assert Store(tmp_path).counts()==s.counts()


def test_api_upload_label_and_training_snapshot(tmp_path):
    s,a,b=trained_store(tmp_path)
    started=threading.Event();release=threading.Event();complete=threading.Event()
    def predictor(store,row):
        return {'label':'air','air_score':.7,'model_version':'test-v1','seen_in_training':row['id'] in store.active_model()['snapshot'],'seconds':.01}
    def trainer(store,progress):
        snapshot={r['id']:r['revision'] for r in store.all(labeled=True)}
        started.set();release.wait(5)
        old=store.active_model();old.update(version='test-v2',snapshot=snapshot)
        store.activate(old);complete.set()
    app=create_app(tmp_path,predictor=predictor,trainer=trainer)
    app.config['TESTING']=True
    client=app.test_client()
    assert client.get('/').status_code==200
    invalid=client.post('/api/upload',data={'image':(io.BytesIO(b'bad'),'bad.jpg')})
    assert invalid.status_code==422
    assert len(s.all())==2
    dup=client.post('/api/upload',data={'image':(io.BytesIO(photo(True)),'air.png')}).get_json()
    assert dup['duplicate'] and dup['prediction']['seen_in_training']
    result=client.post('/api/upload',data={'image':(io.BytesIO(photo(True,shift=3)),'new.png'),'session':'s2'}).get_json()
    assert result['prediction']['label']=='air' and result['label'] is None
    assert client.get('/api/status').get_json()['counts']['pending']==0
    assert client.post(f'/api/images/{result["id"]}/label',json={'label':'air'}).status_code==200
    assert client.post('/api/train',json={}).status_code==202
    assert started.wait(2)
    assert client.post('/api/train',json={}).status_code==409
    # A correction made during training must remain queued for the next model.
    client.post(f'/api/images/{a["id"]}/label',json={'label':'no_air'})
    release.set();assert complete.wait(5)
    assert s.counts()['pending']==1
    assert client.get('/api/download/labels').status_code==200
    assert client.post(f'/api/images/{b["id"]}/label',json={'label':'invalid'}).status_code==422
    assert client.post(f'/api/images/{b["id"]}/label',json={'label':'air'},headers={'Origin':'https://other.example'}).status_code==403


def test_grouped_evaluation_never_splits_a_collection_group():
    rng=np.random.default_rng(42)
    x=rng.normal(size=(12,8));y=np.array([0,1]*6)
    rows=[{'id':str(i),'label':'air' if y[i] else 'no_air','session':'pilot','eval_group':f'fill-{i//4}'} for i in range(12)]
    report=evaluate(x,y,rows)
    assert report['tested']==12 and len(report['folds'])==3
    for fold in report['folds']:
        train=set(fold['train_ids']);test=set(fold['test_ids'])
        assert not train&test
        train_groups={rows[int(i)]['eval_group'] for i in train}
        test_groups={rows[int(i)]['eval_group'] for i in test}
        assert not train_groups&test_groups


def test_failed_training_keeps_previous_model(tmp_path):
    s,a,b=trained_store(tmp_path)
    s.label(a['id'],'no_air')
    # Restore both classes while marking a genuine revision.
    s.label(a['id'],'air')
    def fail(store,progress): raise RuntimeError('simulated training failure')
    app=create_app(tmp_path,predictor=lambda *_:None,trainer=fail)
    c=app.test_client();assert c.post('/api/train',json={}).status_code==202
    deadline=time.time()+3
    while time.time()<deadline:
        state=c.get('/api/status').get_json()['job']
        if state['state']=='failed':break
        time.sleep(.01)
    assert state['state']=='failed'
    assert s.active_model()['version']=='test-v1' and s.counts()['pending']==1
