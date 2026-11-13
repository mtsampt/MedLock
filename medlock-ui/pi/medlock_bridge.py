"""Serve the MedLock patient UI and connect it to the camera station.

Runs the team's camera station (medlock_device) and adds the endpoints that
src/api.js expects, translating station results into pass / fix / unable.
The UI and the API share one address, so no cross-origin requests are needed.

Build the UI first with `npm run build:pi`, then for example:

    python3 pi/medlock_bridge.py --station ~/medlock-station --replay ~/medlock-station/replay
"""
import argparse
import json
import sys
import time
from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[1] / 'dist'

FIX_ACTION = 'Hold the syringe needle-up, tap it so the bubble rises, then push the air out.'

# Station messages (medlock_device/runtime.py) -> short patient wording.
UNABLE_REASONS = [
    ('not seated', 'Syringe not in the dock', 'Press the syringe fully into the dock, then try again.'),
    ('moved', 'The syringe moved', 'Keep the syringe still in the dock and try again.'),
    ('too soft', 'The picture was blurry', 'Take the syringe out, seat it again, and try again.'),
]
UNABLE_DEFAULT = ('The station could not complete the check', 'Try again. If it keeps happening, contact your clinic.')


def to_verdict(result, status):
    """Translate a Station.check() result into the shape src/api.js expects."""
    out = {'volume_ml': None, 'air_ml': None, 'station_state': result.get('state')}
    state = result.get('state') if status == 200 else 'unable'
    if state == 'no_air_detected':
        return {**out, 'verdict': 'pass', 'reason': 'No visible air detected.', 'action': ''}
    if state == 'air_detected':
        return {**out, 'verdict': 'fix', 'reason': 'Air bubble detected', 'action': FIX_ACTION}
    message = (result.get('message') or '').lower()
    reason, action = next(((r, a) for key, r, a in UNABLE_REASONS if key in message), UNABLE_DEFAULT)
    return {**out, 'verdict': 'unable', 'reason': reason, 'action': action}


def main():
    p = argparse.ArgumentParser(description='MedLock patient UI + camera station')
    p.add_argument('--station', type=Path, required=True,
                   help='Folder containing medlock_device/ and medlock_lab/ (the Pi deployment bundle)')
    p.add_argument('--bundle', type=Path, help='Model folder (default: <station>/model)')
    p.add_argument('--replay', type=Path, help='Replay saved photos instead of using the camera')
    p.add_argument('--rotation', type=int, choices=[0, 90, 180, 270], default=0,
                   help='Counterclockwise camera rotation to put plunger top, tip bottom')
    p.add_argument('--threads', type=int, choices=[1, 2, 3, 4], default=2)
    p.add_argument('--port', type=int, default=8768)
    p.add_argument('--log-dir', type=Path, default=Path('logs'))
    args = p.parse_args()

    sys.path.insert(0, str(args.station.resolve()))
    from flask import Flask, jsonify, request, send_from_directory
    from medlock_device.runtime import Engine, PiCamera, ReplayCamera, Station

    if not (UI_DIR / 'index.html').exists():
        p.error(f'No built UI in {UI_DIR}. Run `npm run build:pi` first.')
    bundle = args.bundle or args.station / 'model'
    station = Station(Engine(bundle, args.threads),
                      ReplayCamera(args.replay) if args.replay else PiCamera(),
                      args.log_dir / 'device-events.jsonl', args.rotation)
    ui_log = args.log_dir / 'ui-events.jsonl'

    app = Flask(__name__, static_folder=None)

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/check')
    def check():
        # No seat sensor is wired yet, so the patient tapping "Check syringe"
        # after placing it counts as seated. With a seat pin, Station ignores this.
        result, status = station.check(simulated_seated=True)
        return jsonify(to_verdict(result, status))

    @app.post('/log')
    def log():
        body = request.get_json(silent=True) or {}
        with ui_log.open('a') as f:
            f.write(json.dumps({'event': str(body.get('event')), 'at': body.get('at'),
                                'received': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}) + '\n')
        return jsonify(ok=True)

    @app.get('/')
    def index():
        return send_from_directory(UI_DIR, 'index.html')

    @app.get('/<path:path>')
    def files(path):
        return send_from_directory(UI_DIR, path)

    print(f'MedLock UI: http://127.0.0.1:{args.port}/  ({station.camera.mode})')
    app.run(host='127.0.0.1', port=args.port, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
