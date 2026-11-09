import csv
import json
from pathlib import Path

import pytest
from PIL import Image

from medlock_device.volume import VolumeEstimator
from medlock_lab.imaging import PREPROCESS_VERSION
from scripts.calibrate_volume import calibrate


def calibration():
    return dict(version=1, preprocess_version=PREPROCESS_VERSION, setup_id='fixed-dock', syringe_id='bench-syringe',
                measurement='occupied_barrel_ml', image_size=[600,800], rotation=0,
                slope=-5., intercept=3., max_error_ml=.05,
                feature_min=[.3,.4,.1], feature_max=[.6,.6,.3], volume_range_ml=[0.,1.5],
                training_sessions=['one','two'], evaluation={'count':3,'sessions':['three'],'max_error_ml':.01})


def load(tmp_path, data=None, setup='fixed-dock'):
    path=tmp_path/'calibration.json'
    path.write_text(json.dumps(data or calibration()))
    return VolumeEstimator(path, setup)


def test_interpolation_and_geometry_rejection(tmp_path):
    estimator=load(tmp_path)
    image=Image.new('RGB',(600,800))
    assert estimator.estimate(image,{'stopper_box':[240,300,120,20]}) == 1.
    for box in ([10,300,50,20], [240,100,120,20], [240,300,-120,20], [0,float('nan'),100,20]):
        with pytest.raises(ValueError): estimator.estimate(image,{'stopper_box':box})
    with pytest.raises(ValueError): estimator.estimate(Image.new('RGB',(800,1000)),{'stopper_box':[240,300,120,20]})
    with pytest.raises(ValueError): estimator.estimate(image,{})


@pytest.mark.parametrize('patch',[{'slope':0},{'slope':float('nan')},{'image_size':[600,0]}, {'evaluation':{'count':3,'sessions':['one'],'max_error_ml':.01}}, {'evaluation':{'count':3,'sessions':['three'],'max_error_ml':.5}}])
def test_invalid_or_unvalidated_calibration_is_rejected(tmp_path,patch):
    c=calibration();c.update(patch)
    with pytest.raises(ValueError): load(tmp_path,c)


def test_wrong_setup_rejected(tmp_path):
    with pytest.raises(ValueError): load(tmp_path,setup='different-dock')


def manifest(tmp_path,monkeypatch):
    # Synthetic fixtures exercise fitting/gates; these are not physical calibration evidence.
    monkeypatch.setattr('scripts.calibrate_volume.clean',lambda im:(im,{'warnings':[], 'stopper_box':[240, (100 + im.getpixel((0,0))[0]) - 20, 120,20]}))
    rows=[]
    for i, (session, split, fills) in enumerate([('one','train',[0.,.5,1.]),('two','train',[0.,.5,1.]),('three','evaluate',[0.,.5,1.])]):
        for j,volume in enumerate(fills):
            name=f'{i}-{j}.png'
            image=Image.new('RGB',(600,800),(int(220-volume*100),i,j))
            image.save(tmp_path/name)
            rows.append(dict(image=name,volume_ml=volume,session=session,split=split,air_free='true'))
    path=tmp_path/'fills.csv'
    write_rows(path,rows)
    return path,rows


def write_rows(path,rows):
    with path.open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def test_fit_holdout_error_and_leakage_gates(tmp_path,monkeypatch):
    path,rows=manifest(tmp_path,monkeypatch)
    c=calibrate(path,'fixed-dock','syringe',.05,.01)
    assert c['evaluation']['max_error_ml'] < .0001
    assert c['training_sessions'] == ['one','two']
    rows[-1]['volume_ml']=1.2
    write_rows(path,rows)
    with pytest.raises(ValueError,match='maximum error'): calibrate(path,'fixed-dock','syringe',.05,.01)
    rows[-1]['session']='one';write_rows(path,rows)
    with pytest.raises(ValueError,match='separate sessions'): calibrate(path,'fixed-dock','syringe',.05,.01)


def test_duplicate_pixels_and_air_contaminated_fills_rejected(tmp_path,monkeypatch):
    path,rows=manifest(tmp_path,monkeypatch)
    rows[-1]['image']=rows[0]['image'];write_rows(path,rows)
    with pytest.raises(ValueError,match='Duplicate'): calibrate(path,'dock','syringe',.05,.01)
    rows[-1]['air_free']='false';write_rows(path,rows)
    with pytest.raises(ValueError,match='air_free'): calibrate(path,'dock','syringe',.05,.01)


def test_fitted_calibration_includes_endpoints_without_extrapolation(tmp_path,monkeypatch):
    path,_=manifest(tmp_path,monkeypatch)
    c=calibrate(path,'fixed-dock','syringe',.05,.01)
    estimator=load(tmp_path,c)
    image=Image.new('RGB',(600,800))
    assert estimator.estimate(image,{'stopper_box':[240,300,120,20]}) == pytest.approx(0.,abs=1e-9)
    assert estimator.estimate(image,{'stopper_box':[240,200,120,20]}) == pytest.approx(1.)
