import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.path.exists("/dev/video0"), reason="카메라 하드웨어 없음"
)


def test_camera_capture_returns_jpeg():
    from econ_cam.capture import Camera

    cam = Camera(0, 1920, 1080)
    cam.start()
    try:
        jpeg, pts = cam.capture()
    finally:
        cam.stop()
    assert jpeg[:2] == b"\xff\xd8"  # JPEG SOI 마커
    assert pts > 0


def test_camera_latest_jpeg():
    from econ_cam.capture import Camera

    cam = Camera(0, 1280, 720)
    cam.start()
    try:
        # 프리뷰는 new-sample 푸시 콜백으로 캐시되므로 첫 프레임이 도착할 때까지 잠깐 폴링.
        jpeg = None
        deadline = time.monotonic() + 3.0
        while jpeg is None and time.monotonic() < deadline:
            jpeg = cam.latest_jpeg()
            if jpeg is None:
                time.sleep(0.02)
    finally:
        cam.stop()
    assert jpeg is not None
    assert jpeg[:2] == b"\xff\xd8"


def test_latest_jpeg_none_before_start():
    from econ_cam.capture import Camera

    cam = Camera(0, 1280, 720)
    assert cam.latest_jpeg() is None


@pytest.mark.skipif(not os.path.exists("/dev/video1"), reason="두 번째 카메라 없음")
def test_sync_session_two_cameras():
    from econ_cam.capture import SyncSession

    s = SyncSession([0, 1], 1280, 720, sync_mode=1)
    s.start()
    try:
        result = s.capture()
    finally:
        s.stop()
    assert set(result["images"].keys()) == {0, 1}
    for jpeg in result["images"].values():
        assert jpeg[:2] == b"\xff\xd8"
    assert "spread_ms" in result["stats"]
    assert "std_ms" in result["stats"]
