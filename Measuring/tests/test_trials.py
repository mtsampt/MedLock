from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from medlock_device.trials import append_trial, evaluate, get_state, make_trial, read_jsonl
from test_integration import flow, act, ready, checked

CAL_VERSION='c'*64
CALIBRATION={'training_sessions':['fit-one','fit-two'],'evaluation':{'sessions':['calibration-holdout']},'image_pixel_hashes':['d'*64]}
PI={'system':'Linux','machine':'aarch64','device_model':'Raspberry Pi 3 Model B'}


def trial(index,tests,volume=1.,air=0.,expected=True,predicted=None,detected=None,verdict=None):
    predicted=volume if predicted is None else predicted
    detected=air>=.1 if detected is None else detected
    verdict=verdict or ('fix' if detected or abs(predicted-volume)>.05+1e-9 else 'pass')
    key=f'check-{index}'
    measurement=dict(verdict=verdict,session_id='station',check_id=key,state='air_detected' if detected else 'no_air_detected',
                     label='air' if detected else 'no_air',air_detected=detected,air_score=.9 if detected else .1,
                     volume_ml=predicted,valid=True,syringe_seated=True,image_quality={'warnings':[]},
                     model_version='model-one',calibration_version=CAL_VERSION,mode='Pi CSI camera — rpicam-still')
    return dict(format_version=1,trial_id=f'trial-{index}',session_id='station',check_id=key,tests=tests,
                evidence='physical',station_simulated=False,collector_host=PI,collection_session='independent-day',
                actual_syringe_id='supported-brand',syringe_supported=True,expected_valid=expected,
                blinded=True,reference_volume_ml=volume,reference_air_ml=air,
                configured_target_ml=volume,configured_tolerance_ml=.05,
                capture_pixel_sha256=hashlib.sha256(key.encode()).hexdigest(),seat_to_display_ack_ms=1000.,measurement=measurement)


def report(rows,**kwargs):
    return evaluate(rows,calibration=CALIBRATION,calibration_version=CAL_VERSION,min_latency_trials=20,**kwargs)


def test_replay_cannot_become_physical_acceptance(flow):
    ready(flow);act(flow,'seat');state=checked(flow)
    record=make_trial(state,tests=['combined','latency'],collection_session='replay-session',syringe_id='fixture',supported=True,expected_valid=True,blinded=True,host=PI)
    assert record['evidence']=='replay'
    result=report([record])
    assert result['physical_records']==0 and result['excluded_nonphysical']==1
    assert all(item['status']=='insufficient_evidence' for item in result['criteria'].values())


def test_collector_archives_matching_pixels_and_earliest_ack(flow,tmp_path):
    flow.station.capture_dir=tmp_path/'captures';flow.station.capture_dir.mkdir()
    ready(flow);act(flow,'seat');state=checked(flow)
    events=[dict(event='ui_event',name='result_displayed',session_id=state['session_id'],check_id=state['check_id'],seat_to_display_ack_ms=value) for value in (1100.,900.)]
    record=make_trial(state,tests=['volume','latency'],collection_session='day-three',syringe_id='fixture',supported=True,
                      reference_volume_ml=1.,reference_air_ml=0.,capture_root=flow.station.capture_dir,events=events)
    assert len(record['capture_pixel_sha256'])==64 and record['seat_to_display_ack_ms']==900.
    with pytest.raises(ValueError,match='outside'):make_trial(state,tests=['latency'],collection_session='day-three',syringe_id='fixture',supported=True,capture_root=tmp_path/'different')
    Path(state['result']['capture_file']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='checksum'):make_trial(state,tests=['latency'],collection_session='day-three',syringe_id='fixture',supported=True,capture_root=flow.station.capture_dir)


def test_duplicate_checks_and_partial_files_do_not_silently_append(tmp_path):
    record=trial(0,['latency']);path=tmp_path/'trials.jsonl'
    append_trial(path,record)
    with pytest.raises(ValueError,match='already recorded'):append_trial(path,record)
    assert len(read_jsonl(path))==1
    path.write_text('{"unfinished":')
    with pytest.raises(ValueError,match='incomplete'):read_jsonl(path)
    with pytest.raises(ValueError):append_trial(path,record)
    assert path.read_text()=='{"unfinished":'


def test_calibration_reuse_duplicate_images_and_forged_physical_mode_rejected():
    row=trial(1,['volume'])
    row['collection_session']='fit-one'
    with pytest.raises(ValueError,match='calibration'):report([row])
    row['collection_session']='independent'
    row['capture_pixel_sha256']='d'*64
    with pytest.raises(ValueError,match='calibration'):report([row])
    row['capture_pixel_sha256']='e'*64
    other=trial(2,['volume']);other['capture_pixel_sha256']='e'*64
    with pytest.raises(ValueError,match='Repeated capture'):report([row,other])
    row['collector_host']={'system':'Darwin'}
    with pytest.raises(ValueError,match='provenance'):report([row])


def test_volume_counts_error_and_failed_attempts_without_dilution():
    rows=[trial(i,['volume'],volume=(.5,1.,1.5,2.,2.5)[i//20],predicted=(.5,1.,1.5,2.,2.5)[i//20]+(.1 if i<5 else 0.)) for i in range(100)]
    criterion=report(rows)['criteria']['S1']
    assert criterion['status']=='met_in_recorded_trials'
    assert criterion['metrics']['within_rate']==.95 and criterion['metrics']['usable']==100
    rows[5]['measurement']['volume_ml']+=.1;rows[5]['measurement']['verdict']='fix'
    assert report(rows)['criteria']['S1']['status']=='not_met'
    bad=trial(101,['volume']);bad['measurement'].update(valid=False,volume_ml=None,verdict='unable')
    rows.append(bad)
    criterion=report(rows)['criteria']['S1']
    assert criterion['metrics']['attempts']==101 and criterion['metrics']['excluded']==1
    assert evaluate(rows,min_latency_trials=20)['criteria']['S1']['status']=='insufficient_evidence'


def test_air_unable_results_count_as_misses_and_threshold_bands_required():
    rows=[trial(i,['air'],air=0. if i<20 else .1 if i<60 else .2,expected=i<20) for i in range(100)]
    assert report(rows)['criteria']['S2']['status']=='met_in_recorded_trials'
    for row in rows[20:25]:row['measurement'].update(air_detected=None,label=None,state='unable',verdict='unable',valid=False)
    s2=report(rows)['criteria']['S2']
    assert s2['status']=='not_met' and s2['metrics']['sensitivity']==75/80 and s2['metrics']['unable']==5
    rows[0]['reference_air_ml']=None
    with pytest.raises(ValueError,match='Every air trial'):report(rows)


def test_combined_valid_yield_and_single_false_pass_failure():
    rows=[trial(i,['combined'],air=0. if i<10 else .2,expected=i<10) for i in range(15)]
    rows[0]['measurement']['verdict']='unable'
    assert report(rows)['criteria']['S3']['metrics']['valid_pass_rate']==.9
    assert report(rows)['criteria']['S3']['status']=='met_in_recorded_trials'
    rows[10]['measurement'].update(air_detected=False,air_score=.1,label='no_air',state='no_air_detected',verdict='pass')
    assert report(rows)['criteria']['S3']['status']=='not_met'
    assert report(rows)['criteria']['S3']['metrics']['false_passes']==1
    # Missing provenance must not hide a recorded counterexample to zero false passes.
    assert evaluate(rows,min_latency_trials=20)['criteria']['S3']['status']=='not_met'


def test_latency_requires_declared_count_and_every_display_ack():
    rows=[trial(i,['latency']) for i in range(20)]
    assert evaluate(rows)['criteria']['S5']['status']=='insufficient_evidence'
    assert report(rows)['criteria']['S5']['status']=='met_in_recorded_trials'
    rows[0]['seat_to_display_ack_ms']=10001.
    assert report(rows)['criteria']['S5']['metrics']['fast_rate']==.95
    rows[1]['seat_to_display_ack_ms']=10001.
    assert report(rows)['criteria']['S5']['status']=='not_met'
    rows[1]['seat_to_display_ack_ms']=None
    assert report(rows)['criteria']['S5']['status']=='insufficient_evidence'


def test_unsupported_requires_supported_control_and_two_brands():
    rows=[trial(0,['combined'])]
    for i in (1,2):
        row=trial(i,['unsupported'],expected=False,verdict='unable')
        row.update(syringe_supported=False,actual_syringe_id=f'other-brand-{i}')
        rows.append(row)
    assert report(rows)['criteria']['S7']['status']=='met_in_recorded_trials'
    assert report(rows[1:])['criteria']['S7']['status']=='insufficient_evidence'
    rows[1]['measurement']['verdict']='fix'
    assert report(rows)['criteria']['S7']['status']=='not_met'


def test_invalid_pass_and_reference_labels_are_rejected():
    row=trial(0,['combined'])
    row['measurement']['valid']=False
    with pytest.raises(ValueError,match='Reported pass'):report([row])
    row=trial(0,['combined'],air=.2,expected=True)
    with pytest.raises(ValueError,match='conflicts'):report([row])


def test_nonloopback_recorder_url_is_rejected_before_network():
    for url in ('https://example.com','http://example.com','http://127.0.0.1/?secret=x','http://person:password@127.0.0.1'):
        with pytest.raises(ValueError,match='loopback'):get_state(url)


def test_rejected_gate_retains_loaded_calibration_identity(flow):
    flow.station.volume=SimpleNamespace(version=CAL_VERSION,calibration={'syringe_id':'known','setup_id':'dock'},estimate=lambda *_:pytest.fail('No image should be acquired when unseated'))
    result,_=flow.station.check(False)
    assert result['calibration_version']==CAL_VERSION and result['syringe_profile']=='known' and result['state']=='unable'


def test_air_false_positives_do_not_hide_volume_errors_and_missing_frames_count_as_misses():
    rows=[trial(i,['volume'],volume=(.5,1.,1.5,2.,2.5)[i//20]) for i in range(100)]
    rows[0]['measurement'].update(air_detected=True,label='air',state='air_detected',air_score=.9,verdict='fix')
    assert report(rows)['criteria']['S1']['metrics']['usable']==100
    rows.append(trial(101,['volume'],volume=3.))
    assert report(rows)['criteria']['S1']['metrics']['usable']==100
    assert report(rows)['criteria']['S1']['metrics']['excluded']==1
    air=[trial(i,['air'],air=0. if i<20 else .1 if i<60 else .2,expected=i<20) for i in range(100)]
    for row in air[20:24]:
        row['measurement'].update(state='unable',label=None,air_detected=None,valid=False,verdict='unable',source_sha256=None)
        row['capture_pixel_sha256']=None
    s2=report(air)['criteria']['S2']
    assert s2['metrics']['sensitivity']==.95 and s2['status']=='met_in_recorded_trials'


def test_mixed_models_and_conflicting_simulation_tags_cannot_be_evaluated_as_one_physical_run():
    rows=[trial(i,['latency']) for i in range(2)]
    rows[1]['measurement']['model_version']='different-model'
    with pytest.raises(ValueError,match='one model version'):report(rows)
    rows[1]['measurement']['model_version']='model-one'
    rows[1]['station_simulated']=True
    with pytest.raises(ValueError,match='simulation mode'):report(rows)
