import io
from urllib.parse import urlparse
from flask import Flask, jsonify, request, send_file
from .touchscreen import TouchUI


def create_app(station):
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    app.config['MAX_CONTENT_LENGTH'] = 4096
    touch = TouchUI(station)
    app.config['TOUCH_UI'] = touch

    @app.before_request
    def origin():
        if request.method == 'POST' and request.headers.get('Origin'):
            if urlparse(request.headers['Origin']).netloc != request.host:
                return jsonify(error='Use the station window to capture.'), 403

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.get('/')
    def home():
        return app.send_static_file('touch.html')

    @app.get('/desktop')
    def desktop():
        return app.send_static_file('index.html')

    @app.get('/api/touch')
    def touch_state():
        return jsonify(touch.snapshot())

    @app.post('/api/touch')
    def touch_action():
        body = request.get_json(silent=True) or {}
        if not touch.action(body.get('action'),expected_revision=body.get('expected_revision')):
            return jsonify(error='Action unavailable on this screen.'), 409
        return jsonify(touch.snapshot())

    @app.get('/api/touch/frame')
    def touch_frame():
        stream = io.BytesIO()
        touch.render().save(stream, format='PNG')
        stream.seek(0)
        return send_file(stream, mimetype='image/png')

    @app.get('/api/status')
    def status():
        return jsonify(mode=station.camera.mode, seat_mode='GPIO' if station.seat else 'manual simulation',
                       model=station.engine.metadata, result=station.result)

    @app.post('/api/capture')
    def capture():
        body = request.get_json(silent=True) or {}
        result, code = station.check(body.get('seated') is True)
        return jsonify(result), code

    @app.get('/api/preview')
    def preview():
        if station.preview is None:
            return '', 404
        stream = io.BytesIO()
        station.preview.save(stream, format='PNG')
        stream.seek(0)
        return send_file(stream, mimetype='image/png')

    return app
