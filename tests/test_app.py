import base64
import glob
import json
import os

from econ_cam import app as app_module
from econ_cam import calib_intrinsics as ci


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


# ---- Mode 4: 폴더 기반 보정(Rectification) ----

def _make_session(tmp_path, sub_mode="intrinsic", name="s1", devs=(0,), n_img=4):
    """계산 가능한 세션 폴더: board_config.json + video<n>/ 에 더미 jpg n_img장."""
    sess = tmp_path / sub_mode / name
    sess.mkdir(parents=True)
    (sess / "board_config.json").write_text(json.dumps(
        {"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25.0}))
    for d in devs:
        (sess / f"video{d}").mkdir()
        for i in range(n_img):
            (sess / f"video{d}" / f"frame_{i:03d}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    return sess


def test_rectify_sessions_lists_only_calibratable(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    _make_session(tmp_path, name="good", devs=(0, 3), n_img=4)     # 후보
    _make_session(tmp_path, name="toofew", devs=(1,), n_img=2)     # jpg<4 → 제외
    (tmp_path / "intrinsic" / "nocfg" / "video0").mkdir(parents=True)  # board_config 없음 → 제외
    client = app_module.create_app().test_client()
    body = client.get("/api/rectify/sessions?sub_mode=intrinsic").get_json()
    names = {s["name"]: s for s in body}
    assert set(names) == {"good"}
    assert names["good"]["devs"] == [0, 3]


def test_rectify_compute_per_camera(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    _make_session(tmp_path, name="s1", devs=(0, 3))
    fake = ci.Intrinsics(model="pinhole", K=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], dist=[0] * 5,
                         image_size=(1280, 720), rms=0.3, per_view_errors=[0.3] * 4,
                         n_images=4, board={"board_type": "checkerboard"})
    monkeypatch.setattr(app_module.calib_intrinsics, "compute_intrinsics", lambda *a, **k: fake)
    client = app_module.create_app().test_client()
    r = client.post("/api/rectify/compute", json={"session": "s1", "model": "pinhole"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] and set(body["cameras"]) == {"0", "3"}
    assert body["cameras"]["0"]["rms"] == 0.3
    assert body["cameras"]["0"]["verdict"]["level"] == "excellent"
    assert os.path.exists(str(tmp_path / "intrinsic" / "s1" / "video0_pinhole.json"))
    assert os.path.exists(str(tmp_path / "intrinsic" / "s1" / "video3_pinhole.json"))
    r2 = client.post("/api/rectify/compute", json={"session": "s1", "model": "pinhole"})
    assert r2.get_json()["cameras"]["0"]["cached"] is True


def test_rectify_compute_empty_folder_400(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    sess = tmp_path / "intrinsic" / "empty"
    sess.mkdir(parents=True)
    (sess / "board_config.json").write_text(json.dumps(
        {"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25.0}))
    client = app_module.create_app().test_client()
    r = client.post("/api/rectify/compute", json={"session": "empty", "model": "pinhole"})
    assert r.status_code == 400 and r.get_json()["ok"] is False


def test_rectify_session_status(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    sess = _make_session(tmp_path, name="s1", devs=(0, 3))
    intr = ci.Intrinsics(model="pinhole", K=[[1000, 0, 960], [0, 1000, 540], [0, 0, 1]],
                         dist=[-0.3, 0.1, 0, 0, 0], image_size=(1920, 1080), rms=0.62,
                         per_view_errors=[0.4, 0.55, 1.8], n_images=3,
                         board={"board_type": "checkerboard"})
    ci.save_intrinsics(str(sess / "video0_pinhole.json"), intr)     # video0만 계산됨
    client = app_module.create_app().test_client()
    body = client.get("/api/rectify/session_status?session=s1&model=pinhole").get_json()
    assert body["cameras"]["0"]["has"] is True
    assert body["cameras"]["0"]["verdict"]["level"] == "good"
    assert body["cameras"]["0"]["K"][0][0] == 1000
    assert body["cameras"]["3"]["has"] is False


def test_rectify_stream_needs_session_and_intrinsic(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    _make_session(tmp_path, name="s1", devs=(0,))
    client = app_module.create_app().test_client()
    assert client.get("/api/rectify/stream/0").status_code == 404              # session 파라미터 없음
    r = client.get("/api/rectify/stream/0?session=s1&model=pinhole")
    assert r.status_code == 404 and "intrinsic" in r.get_data(as_text=True)    # 파일 없음


def test_calib_frame_serves_stored_image(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    _make_session(tmp_path, name="s1", devs=(0,), n_img=3)   # frame_000..002 (더미 jpg)
    client = app_module.create_app().test_client()
    r = client.get("/api/calib/frame/intrinsic/s1/0/1")       # 정렬 1번째 프레임
    assert r.status_code == 200
    assert r.mimetype == "image/jpeg"
    assert r.get_data() == b"\xff\xd8\xff\xd9"
    assert client.get("/api/calib/frame/intrinsic/s1/0/9").status_code == 404   # 범위 초과
    assert client.get("/api/calib/frame/bogus/s1/0/0").status_code == 400       # 잘못된 sub_mode


def test_rectify_sync_stream_404_without_session():
    client = app_module.create_app().test_client()
    assert client.get("/api/rectify/sync/stream/0?session=s1&model=pinhole").status_code == 404


def test_rectify_multi_toggle(monkeypatch):
    monkeypatch.setattr(app_module.capture, "SyncSession", _FakeSession)
    client = app_module.create_app().test_client()
    r = client.post("/api/rectify/multi_toggle", json={"on": True})
    assert r.get_json() == {"ok": True, "on": True}
    r2 = client.post("/api/rectify/multi_toggle", json={"on": False})
    assert r2.get_json()["on"] is False


def test_single_stream_blocked_while_sync_active(monkeypatch):
    # 싱크 세션이 장치를 잡은 동안 단일 스트림 라우트는 409(장치 이중 오픈 방지)
    monkeypatch.setattr(app_module.capture, "SyncSession", _FakeSession)
    client = app_module.create_app().test_client()
    client.post("/api/sync/start", json={"devices": [0, 1]})
    assert client.get("/api/stream/0/mjpeg").status_code == 409
    assert client.get("/api/rectify/stream/0").status_code == 409
