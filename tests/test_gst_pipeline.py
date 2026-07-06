from econ_cam.gst_pipeline import preview_pipeline, sync_pipeline


def test_preview_pipeline_contains_device_and_caps():
    p = preview_pipeline(0, 1920, 1080)
    assert "v4l2src device=/dev/video0" in p
    assert "format=UYVY" in p
    assert "width=1920,height=1080" in p
    assert "nvvidconv" in p
    assert "nvjpegenc" in p


def test_preview_pipeline_tees_preview_and_capture():
    p = preview_pipeline(0, 1920, 1080)
    assert "tee name=t" in p
    # 원본 소스는 1회만, 프리뷰/캡처 두 appsink로 분기
    assert p.count("v4l2src") == 1
    assert "appsink name=preview" in p
    assert "appsink name=capture" in p


def test_preview_pipeline_downscales_only_preview_branch():
    p = preview_pipeline(0, 1920, 1080)
    # 프리뷰 갈래만 저해상도로 다운스케일
    assert "width=640,height=360" in p
    # 원본 캡처 갈래는 valve로 게이트, 다운스케일 없음
    assert "valve name=capgate drop=true" in p


def test_preview_pipeline_custom_preview_resolution():
    p = preview_pipeline(3, 1280, 720, preview_width=960, preview_height=540)
    assert "device=/dev/video3" in p
    assert "width=960,height=540" in p


def test_sync_pipeline_has_one_branch_per_device():
    p = sync_pipeline([0, 2], 1920, 1080)
    assert p.count("v4l2src") == 2
    assert "device=/dev/video0" in p
    assert "device=/dev/video2" in p
    assert "appsink name=sink0" in p
    assert "appsink name=sink2" in p
