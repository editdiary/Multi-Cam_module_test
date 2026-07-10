from econ_cam.app import create_app


def test_index_served():
    client = create_app().test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "다중 동기 촬영" in html
    assert "캘리브레이션" in html
    assert "/static/app.js" in html
    assert 'id="resolution"' in html


def test_index_has_rectify_tab():
    html = create_app().test_client().get("/").get_data(as_text=True)
    assert 'data-mode="rectify"' in html
    assert "보정 확인" in html


def test_rectify_single_has_camera_and_toggle():
    html = create_app().test_client().get("/").get_data(as_text=True)
    assert 'id="rect-single-cam"' in html   # 프리뷰 카메라 드롭다운
    assert 'id="rect-toggle"' in html        # 보정 표시 토글


def test_rectify_has_quality_panel():
    html = create_app().test_client().get("/").get_data(as_text=True)
    assert 'id="rect-quality"' in html
