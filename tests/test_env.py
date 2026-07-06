def test_gstreamer_available():
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    assert Gst is not None


def test_gstapp_available():
    import gi
    gi.require_version("GstApp", "1.0")
    from gi.repository import GstApp
    assert GstApp is not None


def test_flask_available():
    import flask
    from importlib.metadata import version
    assert version("flask")


def test_package_importable():
    import econ_cam
    assert econ_cam is not None
