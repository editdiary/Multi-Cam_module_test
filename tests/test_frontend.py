from econ_cam.app import create_app


def test_index_served():
    client = create_app().test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "다중 동기 촬영" in html
    assert "캘리브레이션" in html
    assert "/static/app.js" in html
