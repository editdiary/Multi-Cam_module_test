import os

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
        jpeg = cam.latest_jpeg()
    finally:
        cam.stop()
    assert jpeg is not None
    assert jpeg[:2] == b"\xff\xd8"


@pytest.mark.skipif(not os.path.exists("/dev/video1"), reason="두 번째 카메라 없음")
def test_sync_capture_two_cameras():
    from econ_cam.capture import sync_capture

    result = sync_capture([0, 1], 1280, 720, sync_mode=1)
    assert set(result["images"].keys()) == {0, 1}
    for jpeg in result["images"].values():
        assert jpeg[:2] == b"\xff\xd8"
    assert "spread_ms" in result["stats"]
    assert "std_ms" in result["stats"]
