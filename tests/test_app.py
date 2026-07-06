import base64
import glob
import os

from econ_cam import app as app_module


def test_jpeg_to_data_uri():
    uri = app_module.jpeg_to_data_uri(b"\xff\xd8")
    assert uri == "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8").decode()


def test_capture_multi(monkeypatch):
    fake = {
        "images": {0: b"\xff\xd8zero", 1: b"\xff\xd8one"},
        "timestamps": {0: 10.000, 1: 10.002},
        "stats": {"per_camera": {0: 0.0, 1: 2.0},
                  "spread_ms": 2.0, "std_ms": 1.0, "ref_dev": 0},
    }
    monkeypatch.setattr(app_module.capture, "sync_capture", lambda *a, **k: fake)
    client = app_module.create_app().test_client()
    resp = client.post("/api/capture", json={"mode": "multi", "devices": [0, 1]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body["images"].keys()) == {"0", "1"}
    assert body["images"]["0"].startswith("data:image/jpeg;base64,")
    assert body["stats"]["spread_ms"] == 2.0
    assert body["stats"]["per_camera"]["1"] == 2.0


def test_save_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "CAPTURE_DIR", str(tmp_path))
    fake = {
        "images": {0: b"\xff\xd8AAA"},
        "timestamps": {0: 1.0},
        "stats": {"per_camera": {0: 0.0}, "spread_ms": 0.0, "std_ms": 0.0, "ref_dev": 0},
    }
    monkeypatch.setattr(app_module.capture, "sync_capture", lambda *a, **k: fake)
    client = app_module.create_app().test_client()
    client.post("/api/capture", json={"mode": "multi", "devices": [0]})
    resp = client.post("/api/save")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    jpgs = glob.glob(os.path.join(str(tmp_path), "*", "video0.jpg"))
    reports = glob.glob(os.path.join(str(tmp_path), "*", "sync_report.json"))
    assert len(jpgs) == 1
    assert len(reports) == 1


def test_cameras_route(monkeypatch):
    monkeypatch.setattr(app_module.controls, "detect_cameras",
                        lambda: [{"dev": 0, "name": "ar0234", "label": "Camera 0"}])
    client = app_module.create_app().test_client()
    body = client.get("/api/cameras").get_json()
    assert body[0]["dev"] == 0
