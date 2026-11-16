"""HTTP + Server-Sent Events front for the Controller; also serves the React UI."""
from __future__ import annotations

import json
import queue
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request, send_from_directory

from .controller import Controller

_EVENT_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

_FALLBACK = """<!doctype html><meta charset=utf-8><title>MedLock</title>
<body style="font:16px system-ui;margin:2rem"><h1>MedLock station is running</h1>
<p>The patient UI has not been built yet. In <code>medlock-ui/</code> run
<code>npm ci &amp;&amp; npm run build:station</code>, then reload.</p>
<p>API: <a href="/api/state">/api/state</a></p>"""


def create_app(controller: Controller, ui_dir: Path, ui_log: Path) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 4096
    log_lock = threading.Lock()
    ui_log.parent.mkdir(parents=True, exist_ok=True)

    @app.before_request
    def same_origin_only():
        if request.method == "POST" and request.headers.get("Origin"):
            if urlparse(request.headers["Origin"]).netloc != request.host:
                return jsonify(error="Use the station window."), 403

    @app.after_request
    def headers(resp):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'")
        return resp

    # ---- API ------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return jsonify(ok=True)

    @app.get("/api/state")
    def state():
        return jsonify(controller.snapshot())

    @app.get("/api/events")
    def events():
        q = controller.subscribe()          # subscribe first so no update is missed

        def stream():
            try:
                yield "retry: 1000\n\n"
                yield f"data: {json.dumps(controller.snapshot())}\n\n"
                while True:
                    try:
                        snap = q.get(timeout=15)
                    except queue.Empty:
                        yield ": ping\n\n"
                        continue
                    yield f"data: {json.dumps(snap)}\n\n"
            finally:
                controller.unsubscribe(q)

        resp = Response(stream(), mimetype="text/event-stream")
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    @app.post("/api/measure")
    def measure():
        if controller.request_measure():
            return jsonify(controller.snapshot()), 202
        return jsonify(error="Not ready to measure.", **controller.snapshot()), 409

    @app.post("/api/acknowledge")
    def acknowledge():
        if controller.acknowledge():
            return jsonify(controller.snapshot())
        return jsonify(error="Nothing to acknowledge.", **controller.snapshot()), 409

    @app.post("/api/sim/seat")
    def sim_seat():
        body = request.get_json(silent=True) or {}
        if not isinstance(body.get("seated"), bool):
            return jsonify(error="Send {\"seated\": true|false}."), 400
        if not controller.set_sim_seat(body["seated"]):
            return jsonify(error="Seat is read from GPIO; it cannot be simulated."), 403
        return jsonify(ok=True)

    @app.post("/api/log")
    def log_event():
        body = request.get_json(silent=True) or {}
        event = body.get("event")
        if not isinstance(event, str) or not _EVENT_RE.match(event):
            return jsonify(error="Bad event name."), 400
        row = {"event": event, "client_at": str(body.get("at", ""))[:40],
               "server_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with log_lock, ui_log.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        return jsonify(ok=True)

    # ---- React UI (built into medlock-ui/dist) ----------------------------
    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def ui(path):
        if path.startswith("api/"):
            return jsonify(error="Not found."), 404
        if not (ui_dir / "index.html").exists():
            return Response(_FALLBACK, mimetype="text/html")
        target = (ui_dir / path).resolve()
        if path and target.is_file() and ui_dir.resolve() in target.parents:
            return send_from_directory(ui_dir, path)
        return send_from_directory(ui_dir, "index.html")

    return app
