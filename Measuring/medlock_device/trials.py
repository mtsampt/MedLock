"""Independent bench-trial records and report-target calculations.

Ground truth is supplied by the experiment operator, never inferred from model
output. These calculations describe recorded samples, not clinical readiness.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import uuid
from urllib.parse import urlparse
from urllib.request import urlopen

from medlock_lab.imaging import decode, pixel_hash

TESTS = {'volume', 'air', 'combined', 'latency', 'unsupported'}
FILLS = (.5, 1., 1.5, 2., 2.5)


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def read_jsonl(path):
    records = []
    if not Path(path).exists():
        return records
    with Path(path).open() as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.endswith('\n'):
                raise ValueError(f'{path}:{line_no}: incomplete record; retry after the writer finishes.')
            try:
                value = json.loads(line)
            except ValueError as exc:
                raise ValueError(f'{path}:{line_no}: invalid JSON.') from exc
            if not isinstance(value, dict):
                raise ValueError(f'{path}:{line_no}: expected a JSON object.')
            records.append(value)
    return records


def environment():
    model_path = Path('/proc/device-tree/model')
    model = model_path.read_text().rstrip('\x00\n') if model_path.is_file() else None
    return {'system': platform.system(), 'machine': platform.machine(), 'device_model': model}


def get_state(url):
    parsed = urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Run the recorder beside the station and use a loopback HTTP URL.')
    with urlopen(url.rstrip('/') + '/api/state', timeout=5) as response:
        return json.load(response)


def make_trial(state, *, tests, collection_session, syringe_id, supported,
               expected_valid=None, reference_volume_ml=None, reference_air_ml=None,
               blinded=False, capture_root=None, events=None, host=None, trial_id=None):
    if not isinstance(state,dict) or not isinstance(state.get('protocol'),dict):
        raise ValueError('Invalid station snapshot.')
    tests = sorted(set(tests))
    if not tests or set(tests) - TESTS:
        raise ValueError('Select a supported trial type.')
    if any(not isinstance(text, str) or not text.strip() or len(text) > 100 for text in (collection_session, syringe_id)):
        raise ValueError('Supply the real collection session and actual syringe identifier.')
    if type(supported) is not bool or expected_valid is not None and type(expected_valid) is not bool:
        raise ValueError('Reference validity and syringe support must be booleans.')
    for value in (reference_volume_ml, reference_air_ml):
        if value is not None and not number(value):
            raise ValueError('Reference quantities must be measured finite nonnegative numbers.')
    if 'volume' in tests and (not number(reference_volume_ml) or reference_air_ml != 0 or supported is not True):
        raise ValueError('Volume trials require a supported syringe, known liquid fill and explicitly zero air.')
    if 'air' in tests and (not number(reference_air_ml) or supported is not True):
        raise ValueError('Air trials need a measured air reference and a supported syringe.')
    if 'combined' in tests and expected_valid is None:
        raise ValueError('Combined trials require independent expected_valid ground truth.')
    if expected_valid is True and (not supported or number(reference_air_ml) and reference_air_ml >= .10):
        raise ValueError('Reference labels conflict: unsupported syringes or >=0.10 mL air cannot be valid.')
    if 'unsupported' in tests and (supported or expected_valid is not False):
        raise ValueError('Unsupported trials require an unsupported syringe and expected_valid=false.')
    result = state.get('result')
    if state.get('screen') != 'result' or not isinstance(result, dict) or result.get('verdict') not in {'pass', 'fix', 'unable'}:
        raise ValueError('Complete a check and record its result before it expires.')
    check_id, session_id = state.get('check_id'), state.get('session_id')
    if not check_id or not session_id or result.get('check_id') != check_id or result.get('session_id') != session_id:
        raise ValueError('Result/session identifiers do not match.')
    if type(state.get('simulated')) is not bool:
        raise ValueError('Station must explicitly identify replay or hardware mode.')
    host = host or environment()
    physical = (state['simulated'] is False and host.get('system') == 'Linux' and
                str(host.get('device_model', '')).startswith('Raspberry Pi'))
    evidence = 'physical' if physical else 'replay' if state['simulated'] else 'unverified_hardware'
    capture_hash = None
    if capture_root is not None and result.get('capture_file'):
        root = Path(capture_root).resolve()
        path = Path(result['capture_file']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Station capture is outside the operator-specified capture root.')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != result.get('source_sha256'):
            raise ValueError('Archived capture does not match the check checksum.')
        rotation = result.get('rotation')
        if type(rotation) is not int or rotation not in (0, 90, 180, 270):
            raise ValueError('Measurement lacks its camera rotation.')
        capture_hash = pixel_hash(decode(raw).rotate(rotation, expand=True))
    acks = [event['seat_to_display_ack_ms'] for event in (events or [])
            if event.get('event') == 'ui_event' and event.get('name') in {'result_displayed', 'native_result_displayed'}
            and event.get('session_id') == session_id and event.get('check_id') == check_id
            and number(event.get('seat_to_display_ack_ms'))]
    if trial_id is not None and (not isinstance(trial_id,str) or not trial_id.strip() or len(trial_id)>100):
        raise ValueError('Trial ID must contain 1–100 characters.')
    return dict(format_version=1, trial_id=trial_id or uuid.uuid4().hex,
                recorded_at=datetime.now(timezone.utc).isoformat(), collection_session=collection_session,
                tests=tests, evidence=evidence, station_simulated=state['simulated'], collector_host=host, session_id=session_id, check_id=check_id,
                actual_syringe_id=syringe_id, syringe_supported=supported, expected_valid=expected_valid,
                configured_target_ml=state.get('protocol',{}).get('target_volume_ml'),
                configured_tolerance_ml=state.get('protocol',{}).get('tolerance_ml'),
                blinded=blinded is True, reference_volume_ml=reference_volume_ml,
                reference_air_ml=reference_air_ml, capture_pixel_sha256=capture_hash,
                seat_to_display_ack_ms=min(acks) if acks else None, measurement=result)


def append_trial(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # One locked append protects against two collector processes recording a check.
    with path.open('a+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        existing = [json.loads(line) for line in stream]
        if any(row.get('trial_id') == record['trial_id'] or
               (row.get('session_id'), row.get('check_id')) == (record['session_id'], record['check_id']) for row in existing):
            raise ValueError('This trial ID or station check is already recorded; do not count it twice.')
        stream.write(json.dumps(record, allow_nan=False) + '\n')
        stream.flush()


def _air_observation_valid(measurement):
    air=measurement.get('air_detected')
    quality=measurement.get('image_quality')
    return (type(air) is bool and measurement.get('syringe_seated') is True and
            measurement.get('state')==('air_detected' if air else 'no_air_detected') and
            measurement.get('label')==('air' if air else 'no_air') and
            number(measurement.get('air_score')) and measurement['air_score']<=1 and
            isinstance(quality,dict) and quality.get('warnings')==[])


def _volume_observation_valid(measurement):
    return (_air_observation_valid(measurement) and measurement.get('valid') is True and number(measurement.get('volume_ml')))


def _criterion(metrics, enough, target_met, missing):
    return dict(status='insufficient_evidence' if not enough else 'met_in_recorded_trials' if target_met else 'not_met',
                metrics=metrics, missing=missing)


def evaluate(records, calibration=None, calibration_version=None, min_latency_trials=None):
    """Compute S1/S2/S3/S5/S7 on physical, independent trial records only."""
    if min_latency_trials is not None and (type(min_latency_trials) is not int or min_latency_trials < 1):
        raise ValueError('Choose a positive minimum latency trial count explicitly.')
    seen, ids, pixel_hashes = set(), set(), set()
    for row in records:
        if row.get('format_version') != 1 or not isinstance(row.get('tests'), list) or not row['tests'] or any(not isinstance(x,str) for x in row['tests']) or set(row['tests']) - TESTS:
            raise ValueError('Unsupported trial record schema or test types.')
        for field in ('session_id','check_id','trial_id','collection_session','actual_syringe_id'):
            if not isinstance(row.get(field),str) or not row[field].strip() or len(row[field])>100:
                raise ValueError('Trial identifiers, collection session and actual syringe must be nonempty strings.')
        key = (row.get('session_id'), row.get('check_id'))
        if not all(key) or key in seen or not row.get('trial_id') or row['trial_id'] in ids:
            raise ValueError('Missing or duplicate station check/trial identifiers.')
        seen.add(key); ids.add(row['trial_id'])
        measurement = row.get('measurement')
        if not isinstance(measurement, dict) or measurement.get('verdict') not in {'pass', 'fix', 'unable'} or (measurement.get('session_id'), measurement.get('check_id')) != key:
            raise ValueError('Result envelope does not match its check.')
        if row.get('evidence') not in {'physical', 'replay', 'unverified_hardware'} or type(row.get('syringe_supported')) is not bool:
            raise ValueError('Trial provenance and syringe support must be explicit.')
        if type(row.get('station_simulated')) is not bool or row['evidence']=='physical' and row['station_simulated'] is not False or row['evidence']=='replay' and row['station_simulated'] is not True:
            raise ValueError('Evidence tag conflicts with station simulation mode.')
        if not isinstance(measurement.get('model_version'),str) or not measurement['model_version']:
            raise ValueError('Every trial must identify its air model version.')
        if row['evidence']=='physical':
            host=row.get('collector_host',{})
            if not isinstance(host,dict) or host.get('system')!='Linux' or not str(host.get('device_model','')).startswith('Raspberry Pi') or not isinstance(measurement.get('mode'),str) or 'photo replay' in measurement['mode'].lower():
                raise ValueError('Physical provenance conflicts with collector host or replay mode.')
        if row.get('capture_pixel_sha256') is not None and (not isinstance(row['capture_pixel_sha256'],str) or re.fullmatch('[0-9a-f]{64}',row['capture_pixel_sha256']) is None):
            raise ValueError('Invalid capture pixel SHA-256.')
        if row.get('expected_valid') is not None and type(row['expected_valid']) is not bool:
            raise ValueError('Invalid expected-valid label.')
        if 'combined' in row['tests'] and row.get('expected_valid') is None:
            raise ValueError('Combined trials need independent validity labels.')
        for field in ('reference_volume_ml', 'reference_air_ml', 'seat_to_display_ack_ms'):
            if row.get(field) is not None and not number(row[field]):
                raise ValueError('Trial references/timings must be finite and nonnegative.')
        if 'volume' in row['tests'] and (not number(row.get('reference_volume_ml')) or row.get('reference_air_ml')!=0 or row['syringe_supported'] is not True):
            raise ValueError('Volume trials need known air-free fills in supported syringes.')
        if 'air' in row['tests'] and (not number(row.get('reference_air_ml')) or row['syringe_supported'] is not True):
            raise ValueError('Every air trial needs a measured air quantity and supported syringe.')
        if 'unsupported' in row['tests'] and (row['syringe_supported'] is not False or row.get('expected_valid') is not False):
            raise ValueError('Unsupported trial labels conflict.')
        if row.get('expected_valid') is True and (not row['syringe_supported'] or number(row.get('reference_air_ml')) and row['reference_air_ml']>=.10):
            raise ValueError('Reference validity conflicts with syringe/air ground truth.')
        if measurement['verdict']=='pass':
            target,tolerance=row.get('configured_target_ml'),row.get('configured_tolerance_ml')
            if not _volume_observation_valid(measurement) or measurement.get('air_detected') is not False or not number(target) or target<=0 or not number(tolerance) or not 0<tolerance<target or abs(measurement['volume_ml']-target)>tolerance+1e-9:
                raise ValueError('Reported pass lacks a complete valid measurement and configured target/tolerance.')
        if row['evidence'] == 'physical' and row.get('capture_pixel_sha256'):
            digest = row['capture_pixel_sha256']
            if digest in pixel_hashes:
                raise ValueError('Repeated capture pixels cannot count as independent physical trials.')
            pixel_hashes.add(digest)
    physical = [row for row in records if row['evidence'] == 'physical']
    if len({r['measurement']['model_version'] for r in physical})>1:
        raise ValueError('Evaluate one model version at a time; keep separate trial files for model changes.')
    known_sessions = set((calibration or {}).get('training_sessions', [])) | set((calibration or {}).get('evaluation', {}).get('sessions', []))
    known_pixels = set((calibration or {}).get('image_pixel_hashes', []))
    for row in physical:
        if row['collection_session'] in known_sessions or row.get('capture_pixel_sha256') in known_pixels:
            raise ValueError('A test trial reuses a calibration session/image; collect independent test data.')
    def rows(kind): return [row for row in physical if kind in row['tests']]
    def measured(row): return row['measurement']
    def image_evidence(row):
        m=measured(row)
        return bool(row.get('capture_pixel_sha256')) or (m.get('state')=='unable' and m['verdict']=='unable' and m.get('source_sha256') is None)
    def independent(row):
        m=measured(row)
        return bool(image_evidence(row) and row.get('collection_session') and calibration_version and
                    m.get('calibration_version') == calibration_version)

    volume = rows('volume')
    usable = [r for r in volume if r.get('syringe_supported') is True and r.get('reference_air_ml') == 0 and
              number(r.get('reference_volume_ml')) and any(abs(r['reference_volume_ml']-fill)<1e-9 for fill in FILLS) and _volume_observation_valid(measured(r))]
    by_fill = {str(fill): {'attempts': sum(abs(r.get('reference_volume_ml', -100)-fill)<1e-9 for r in volume if number(r.get('reference_volume_ml'))),
                           'usable': sum(abs(r['reference_volume_ml']-fill)<1e-9 for r in usable)} for fill in FILLS}
    errors = [abs(measured(r)['volume_ml']-r['reference_volume_ml']) for r in usable]
    accurate = sum(error <= .05 + 1e-9 for error in errors)
    missing = []
    if any(counts['usable'] < 20 for counts in by_fill.values()): missing.append('Need 20 usable independent observations at each of 0.5, 1.0, 1.5, 2.0 and 2.5 mL; all failed attempts remain reported.')
    if not calibration_version or any(not independent(r) for r in usable): missing.append('Supply the matching calibration and archived image evidence for every usable volume trial.')
    s1 = _criterion(dict(attempts=len(volume), usable=len(usable), excluded=len(volume)-len(usable), by_fill=by_fill,
                         within_005_ml=accurate, within_rate=accurate/len(errors) if errors else None,
                         max_error_ml=max(errors) if errors else None), not missing,
                    bool(errors) and accurate/len(errors) >= .95, missing)

    air = rows('air')
    positive = [r for r in air if number(r.get('reference_air_ml')) and r['reference_air_ml'] >= .10]
    detected = sum(_air_observation_valid(measured(r)) and measured(r).get('air_detected') is True for r in positive)
    bands = Counter('below' if r['reference_air_ml'] < .10 else 'at' if abs(r['reference_air_ml']-.10)<1e-9 else 'above' for r in air if number(r.get('reference_air_ml')))
    missing = []
    if len(air)<100 or len(bands)<3 or not positive: missing.append('Need >=100 trials with measured air below, at and above 0.10 mL.')
    if any(not image_evidence(r) or not r.get('collection_session') for r in air): missing.append('Archive independent test captures and identify the real collection sessions.')
    s2 = _criterion(dict(attempts=len(air), air_bands=dict(bands), positive_references=len(positive), detected=detected,
                         sensitivity=detected/len(positive) if positive else None,
                         unable=sum(measured(r)['verdict']=='unable' for r in air)), not missing,
                    bool(positive) and detected/len(positive) >= .95, missing)

    combined = rows('combined')
    valid = [r for r in combined if r['expected_valid'] is True]
    invalid = [r for r in combined if r['expected_valid'] is False]
    valid_passes = sum(measured(r)['verdict']=='pass' for r in valid)
    false_passes = sum(measured(r)['verdict']=='pass' for r in invalid)
    missing = []
    if not valid or not invalid: missing.append('Need independently labelled valid and invalid combined trials.')
    if any(not r.get('blinded') for r in combined): missing.append('Combined test labels must come from the declared blinded protocol.')
    if not calibration_version or any(not independent(r) for r in combined): missing.append('Need the matching calibration and independent archived images for combined trials.')
    s3 = _criterion(dict(attempts=len(combined), valid_cases=len(valid), invalid_cases=len(invalid), valid_passes=valid_passes,
                         valid_pass_rate=valid_passes/len(valid) if valid else None, false_passes=false_passes,
                         unable=sum(measured(r)['verdict']=='unable' for r in combined)), not missing or false_passes>0,
                    bool(valid) and false_passes==0 and valid_passes/len(valid)>=.90, missing)

    latency = rows('latency')
    timed = [r for r in latency if number(r.get('seat_to_display_ack_ms'))]
    fast = sum(r['seat_to_display_ack_ms']<=10000 for r in timed)
    missing = []
    if min_latency_trials is None: missing.append('Declare --min-latency-trials; the report does not specify its sample count.')
    if min_latency_trials is not None and len(timed)<min_latency_trials: missing.append('Insufficient timed physical trials for the declared sample count.')
    if len(timed)!=len(latency): missing.append('Every latency attempt needs its matching display acknowledgement.')
    s5 = _criterion(dict(attempts=len(latency), timed=len(timed), at_most_10s=fast,
                         fast_rate=fast/len(timed) if timed else None,
                         max_ms=max((r['seat_to_display_ack_ms'] for r in timed),default=None)), not missing,
                    bool(timed) and fast/len(timed)>=.95, missing)

    unsupported = rows('unsupported')
    brands = {r.get('actual_syringe_id') for r in unsupported if r.get('syringe_supported') is False}
    rejected = sum(measured(r)['verdict']=='unable' for r in unsupported)
    missing = []
    if len(brands)<2: missing.append('Need two identified unsupported syringe brands.')
    if not any(measured(r)['verdict']=='pass' and independent(r) for r in valid): missing.append('A matching calibrated supported-syringe control must pass; all-unable software is not evidence of discrimination.')
    s7 = _criterion(dict(attempts=len(unsupported), actual_syringes=sorted(str(x) for x in brands), unable=rejected), not missing or rejected<len(unsupported),
                    bool(unsupported) and rejected==len(unsupported), missing)
    return dict(format_version=1, scope='Recorded bench trials only; not physical or clinical certification.',
                total_records=len(records), physical_records=len(physical), excluded_nonphysical=len(records)-len(physical),
                criteria={'S1':s1,'S2':s2,'S3':s3,'S5':s5,'S7':s7},
                manual_evidence_required=['S4 seat/load/lift/fault tests','S6 comprehension sessions','S8 actual BOM cost','Pi installation, reboot recovery, optical setup and independent image-quality checks'])
