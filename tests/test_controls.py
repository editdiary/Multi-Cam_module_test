from econ_cam.controls import parse_card_type, parse_resolutions, parse_controls

INFO_SAMPLE = """Driver Info:
\tDriver name      : tegra-video
\tCard type        : vi-output, ar0234 11-0042
\tBus info         : platform:tegra-capture-vi:2
"""

FORMATS_SAMPLE = """ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'UYVY' (UYVY 4:2:2)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.008s (120.000 fps)
\t\tSize: Discrete 1920x1080
\t\t\tInterval: Discrete 0.015s (65.000 fps)
\t\tSize: Discrete 1920x1200
\t\t\tInterval: Discrete 0.017s (60.000 fps)
\t[1]: 'NV16' (Y/CbCr 4:2:2)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.008s (120.000 fps)
"""

CTRLS_SAMPLE = """
User Controls

                     brightness 0x00980900 (int)    : min=-15 max=15 step=1 default=0 value=0 flags=slider
        white_balance_automatic 0x0098090c (bool)   : default=1 value=1

Camera Controls

                  exposure_auto 0x009a0901 (menu)   : min=0 max=2 default=0 value=0 (Full FOV Auto Mode)
\t\t\t\t0: Full FOV Auto Mode
\t\t\t\t1: Manual Mode
                     frame_sync 0x009a092a (menu)   : min=0 max=2 default=0 value=0 (Disable Frame Sync)
\t\t\t\t0: Disable Frame Sync
\t\t\t\t1: Frame Sync 30 Hz
"""


def test_parse_card_type():
    assert parse_card_type(INFO_SAMPLE) == "vi-output, ar0234 11-0042"


def test_parse_card_type_missing():
    assert parse_card_type("no card here") == "Unknown"


def test_parse_resolutions_dedup_and_order():
    res = parse_resolutions(FORMATS_SAMPLE)
    assert res == [(1280, 720), (1920, 1080), (1920, 1200)]


def test_parse_controls_types_and_values():
    ctrls = parse_controls(CTRLS_SAMPLE)
    assert ctrls["brightness"] == {
        "type": "int", "min": -15, "max": 15, "step": 1, "default": 0, "value": 0,
    }
    assert ctrls["white_balance_automatic"]["type"] == "bool"
    assert ctrls["white_balance_automatic"]["value"] == 1
    assert ctrls["frame_sync"]["type"] == "menu"
    assert ctrls["frame_sync"]["max"] == 2
    # 메뉴 옵션 서브라인(0:, 1:)은 컨트롤로 파싱되면 안 됨
    assert "0" not in ctrls and "1" not in ctrls
