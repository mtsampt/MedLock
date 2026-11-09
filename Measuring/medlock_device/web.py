"""Local API and production React assets on one origin."""
import io
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file, send_from_directory

from .state_machine import FlowError, Session


def create_app(station, session=None, ui_dir=None):
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 4096
    session = session or Session(station)
    app.config['SESSION_CONTROLLER'] = session
    ui_dir = Path(ui_dir or Path(__file__).with_name('ui')).resolve()

    @app.before_request
    def origin():
        if request.method == 'POST' and request.headers.get('Origin'):
            if urlparse(request.headers['Origin']).netloc != request.host:
                return jsonify(error='Use the station window.'), 403

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.errorhandler(FlowError)
    def flow_error(exc):
        return jsonify(error=str(exc), state=session.snapshot()), exc.code

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise FlowError('Expected a JSON object.', 400)
        return value

    @app.get('/')
    def home():
        if not (ui_dir / 'index.html').is_file():
            return 'Build medlock-ui and pass --ui-dir medlock-ui/dist. See docs/INTEGRATION.md.', 503
        return send_from_directory(ui_dir, 'index.html')

    @app.get('/assets/<path:filename>')
    def assets(filename):
        return send_from_directory(ui_dir / 'assets', filename)

    @app.get('/api/state')
    def state():
        return jsonify(session.snapshot())

    @app.post('/api/action')
    def action():
        data = body()
        return jsonify(session.action(data.get('action'), data.get('session_id'), data.get('revision')))

    @app.post('/api/check')
    def check():
        data = body()
        return jsonify(session.action('capture', data.get('session_id'), data.get('revision'))), 202

    @app.get('/api/supplies')
    def supplies():
        return jsonify(session.supplies())

    @app.post('/api/log')
    def log():
        data = body()
        session.log_client_event(data.get('event'), data.get('check_id'))
        return jsonify(ok=True)

    @app.get('/api/status')
    def status():
        return jsonify(mode=station.camera.mode, model=station.engine.metadata,
                       state=session.snapshot(), capabilities={'volume': station.volume is not None, 'air_volume': False})

    @app.get('/api/preview')
    def preview():
        snapshot = session.snapshot()
        if station.preview is None or snapshot['screen'] != 'result':
            return '', 404
        stream = io.BytesIO()
        station.preview.save(stream, format='PNG')
        stream.seek(0)
        return send_file(stream, mimetype='image/png')

    @app.post('/api/capture')
    def old_capture():
        raise FlowError('Use the guided flow and POST /api/check with its current session/revision.', 410)

    return app
