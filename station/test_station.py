import json
import time
from pathlib import Path

import pytest

from station import ROOT
from station.controller import Controller
from station.measuring_acquisition import MeasuringAcquisition, SimSeat
from station.server import create_app


class FakeStation:
    """Same surface the Station exposes to MeasuringAcquisition."""
    seat = None
    preview = None

    def __init__(self, result=None, delay=0.0):
        self.result = result or {"state": "no_air_detected", "label": "no_air", "air_score": 0.02}
        self.delay = delay
        self.calls = 0

    def check(self, simulated_seated):
        self.calls += 1
        time.sleep(self.delay)
        return dict(self.result), 200


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def rig(tmp_path):
    def make(result=None, delay=0.0):
        station = FakeStation(result, delay)
        sim = SimSeat()
        c = Controller(MeasuringAcquisition(station, lambda: sim.seated), sim_seat=sim, poll_interval=0.01)
        c.start()
        made.append(c)
        return c, station, sim
    made = []
    yield make
    for c in made:
        c.stop()


def test_full_cycle_pushes_every_state(rig):
    c, station, sim = rig()
    q = c.subscribe()
    sim.set(True)
    assert wait_for(lambda: c.snapshot()["state"] == "SEATED")
    assert c.request_measure()
    assert wait_for(lambda: c.snapshot()["state"] == "RESULT")
    snap = c.snapshot()
    assert snap["result"]["verdict"] == "pass"
    assert snap["result"]["volume_checked"] is False
    assert c.acknowledge()
    assert wait_for(lambda: c.snapshot()["state"] == "SEATED")
    assert c.snapshot()["result"] is None
    sim.set(False)
    assert wait_for(lambda: c.snapshot()["state"] == "IDLE")

    seen = []
    while not q.empty():
        seen.append(q.get_nowait()["state"])
    assert seen[:4] == ["SEATED", "MEASURING", "RESULT", "SEATED"]
    assert seen[-1] == "IDLE"


def test_air_is_fix_not_pass(rig):
    c, _, sim = rig({"state": "air_detected", "label": "air", "air_score": 0.97})
    sim.set(True)
    assert wait_for(lambda: c.snapshot()["state"] == "SEATED")
    c.request_measure()
    assert wait_for(lambda: c.snapshot()["state"] == "RESULT")
    assert c.snapshot()["result"]["verdict"] == "fix"


def test_station_failure_is_unable_never_pass(rig):
    c, _, sim = rig({"state": "unable", "message": "Image is too soft. Refocus and capture again."})
    sim.set(True)
    assert wait_for(lambda: c.snapshot()["state"] == "SEATED")
    c.request_measure()
    assert wait_for(lambda: c.snapshot()["state"] == "ERROR")
    r = c.snapshot()["result"]
    assert r["verdict"] == "unable" and "soft" in r["reason"]


def test_stale_result_is_not_shown_after_a_failed_run(rig):
    c, station, sim = rig()
    sim.set(True)
    assert wait_for(lambda: c.snapshot()["state"] == "SEATED")
    c.request_measure()
    assert wait_for(lambda: c.snapshot()["state"] == "RESULT")
    c.acknowledge()
    station.result = {"state": "unable", "message": "Camera or inference failed. Check the device log and retry."}
    assert wait_for(lambda: c.snapshot()["state"] == "SEATED")
    c.request_measure()
    assert wait_for(lambda: c.snapshot()["state"] == "ERROR")
    assert c.snapshot()["result"]["verdict"] == "unable"


def test_cannot_measure_unless_seated_or_twice(rig):
    c, station, sim = rig(delay=0.3)
    assert c.request_measure() is False             # IDLE
    sim.set(True)
    assert wait_for(lambda: c.snapshot()["state"] == "SEATED")
    assert c.request_measure() is True
    assert c.request_measure() is False             # already running
    assert wait_for(lambda: c.snapshot()["state"] == "RESULT")
    assert station.calls == 1


def test_removal_during_result_returns_to_idle_and_clears_result(rig):
    c, _, sim = rig()
    sim.set(True)
    assert wait_for(lambda: c.snapshot()["state"] == "SEATED")
    c.request_measure()
    assert wait_for(lambda: c.snapshot()["state"] == "RESULT")
    sim.set(False)
    assert wait_for(lambda: c.snapshot()["state"] == "IDLE")
    assert c.snapshot()["result"] is None


# ---- HTTP layer -------------------------------------------------------------

@pytest.fixture
def client(rig, tmp_path):
    c, station, sim = rig()
    app = create_app(c, tmp_path / "no-dist", tmp_path / "ui.jsonl")
    return app.test_client(), c, tmp_path


def test_http_flow(client):
    http, c, tmp = client
    assert http.get("/api/state").json["state"] == "IDLE"
    assert http.post("/api/measure").status_code == 409
    assert http.post("/api/acknowledge").status_code == 409
    assert http.post("/api/sim/seat", json={"seated": "yes"}).status_code == 400
    assert http.post("/api/sim/seat", json={"seated": True}).status_code == 200
    assert wait_for(lambda: http.get("/api/state").json["state"] == "SEATED")
    assert http.post("/api/measure").status_code == 202
    assert wait_for(lambda: http.get("/api/state").json["state"] == "RESULT")
    assert http.get("/api/state").json["result"]["verdict"] == "pass"
    assert http.post("/api/acknowledge").status_code == 200


def test_sse_sends_snapshot_then_updates(client):
    http, c, _ = client
    resp = http.get("/api/events", buffered=False)
    stream = iter(resp.response)
    assert next(stream) == b"retry: 1000\n\n"
    first = json.loads(next(stream).decode().removeprefix("data: "))
    assert first["state"] == "IDLE"
    http.post("/api/sim/seat", json={"seated": True})
    nxt = json.loads(next(stream).decode().removeprefix("data: "))
    assert nxt["state"] == "SEATED" and nxt["revision"] > first["revision"]
    resp.close()


def test_log_endpoint_validates_and_writes(client):
    http, _, tmp = client
    assert http.post("/api/log", json={"event": "bad event!"}).status_code == 400
    assert http.post("/api/log", json={"event": "check_pass", "at": "x"}).status_code == 200
    assert json.loads((tmp / "ui.jsonl").read_text().splitlines()[0])["event"] == "check_pass"


def test_cross_origin_post_rejected(client):
    http, *_ = client
    r = http.post("/api/sim/seat", json={"seated": True}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_fallback_page_when_ui_not_built(client):
    http, *_ = client
    assert b"npm run build:station" in http.get("/").data
    assert http.get("/api/nope").status_code == 404


# ---- Real Measuring pipeline (skipped if model/photos are absent) -----------

BUNDLE = ROOT / "Measuring/outputs/pi-bundle"
PHOTOS = ROOT / "Measuring/outputs/medlock-pilot-2026-10-21/images"


@pytest.mark.skipif(not (BUNDLE / "features.onnx").exists() or not PHOTOS.exists(),
                    reason="model bundle or pilot photos not present")
def test_real_model_end_to_end(tmp_path):
    pytest.importorskip("cv2")
    from medlock_device.runtime import Engine, ReplayCamera, Station

    st = Station(Engine(BUNDLE, 2), ReplayCamera(PHOTOS), tmp_path / "ev.jsonl", rotation=0)
    sim = SimSeat()
    c = Controller(MeasuringAcquisition(st, lambda: sim.seated), sim_seat=sim, poll_interval=0.01)
    c.start()
    try:
        sim.set(True)
        assert wait_for(lambda: c.snapshot()["state"] == "SEATED")
        assert c.request_measure()
        assert wait_for(lambda: c.snapshot()["state"] in ("RESULT", "ERROR"), timeout=30)
        snap = c.snapshot()
        print(snap)
        assert snap["state"] == "RESULT", snap
        assert snap["result"]["verdict"] in ("pass", "fix")
        assert snap["result"]["volume_checked"] is False
        assert (tmp_path / "ev.jsonl").read_text().strip()      # Measuring's own log still written
    finally:
        c.stop()
