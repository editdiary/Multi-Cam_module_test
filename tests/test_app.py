import base64
import glob
import os

from econ_cam import app as app_module


def test_jpeg_to_data_uri():
    uri = app_module.jpeg_to_data_uri(b"\xff\xd8")
    assert uri == "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8").decode()


class _FakeSession:
    def __init__(self, devs, *a, **k):
        self._devs = [int(d) for d in devs]

    def start(self):
        pass

    def stop(self):
        pass

    def capture(self):
        images = {d: b"\xff\xd8" + bytes([d]) for d in self._devs}
        per_camera = {d: float(d) for d in self._devs}  # dev0=0.0, dev1=1.0, ...
        return {
            "images": images,
            "timestamps": {d: 10.0 + d / 1000.0 for d in self._devs},
            "stats": {"per_camera": per_camera, "spread_ms": float(max(self._devs)),
                      "std_ms": 1.0, "ref_dev": self._devs[0]},
        }


def test_sync_capture(monkeypatch):
    monkeypatch.setattr(app_module.capture, "SyncSession", _FakeSession)
    client = app_module.create_app().test_client()
    client.post("/api/sync/start", json={"devices": [0, 1]})
    resp = client.post("/api/sync/capture", json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body["images"].keys()) == {"0", "1"}
    assert body["images"]["0"].startswith("data:image/jpeg;base64,")
    assert body["stats"]["spread_ms"] == 1.0
    assert body["stats"]["per_camera"]["1"] == 1.0


def test_sync_capture_without_session(monkeypatch):
    client = app_module.create_app().test_client()
    resp = client.post("/api/sync/capture", json={})
    assert resp.status_code == 400


def test_save_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "CAPTURE_DIR", str(tmp_path))
    monkeypatch.setattr(app_module.capture, "SyncSession", _FakeSession)
    client = app_module.create_app().test_client()
    client.post("/api/sync/start", json={"devices": [0]})
    client.post("/api/sync/capture", json={})
    resp = client.post("/api/save")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    jpgs = glob.glob(os.path.join(str(tmp_path), "*", "video0.jpg"))
    reports = glob.glob(os.path.join(str(tmp_path), "*", "sync_report.json"))
    assert len(jpgs) == 1
    assert len(reports) == 1


def test_get_resolution_returns_current():
    client = app_module.create_app(width=1280, height=720).test_client()
    body = client.get("/api/resolution").get_json()
    assert body == {"width": 1280, "height": 720}


def test_cameras_route(monkeypatch):
    monkeypatch.setattr(app_module.controls, "detect_cameras",
                        lambda: [{"dev": 0, "name": "ar0234", "label": "Camera 0"}])
    client = app_module.create_app().test_client()
    body = client.get("/api/cameras").get_json()
    assert body[0]["dev"] == 0
