from econ_cam.gst_pipeline import preview_pipeline, sync_pipeline


def test_preview_pipeline_contains_device_and_caps():
    p = preview_pipeline(0, 1920, 1080)
    assert "v4l2src device=/dev/video0" in p
    assert "format=UYVY" in p
    assert "width=1920,height=1080" in p
    assert "nvvidconv" in p
    assert "nvjpegenc" in p
    assert "appsink name=sink" in p


def test_preview_pipeline_custom_sink_name():
    p = preview_pipeline(3, 1280, 720, sink_name="sink3")
    assert "device=/dev/video3" in p
    assert "appsink name=sink3" in p


def test_sync_pipeline_has_one_branch_per_device():
    p = sync_pipeline([0, 2], 1920, 1080)
    assert p.count("v4l2src") == 2
    assert "device=/dev/video0" in p
    assert "device=/dev/video2" in p
    assert "appsink name=sink0" in p
    assert "appsink name=sink2" in p
