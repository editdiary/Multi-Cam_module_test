import cv2
import numpy as np
from econ_cam.calib_board import parse_board_config
from econ_cam.calib_detect import (detect_board, quality_metrics, pose_descriptor,
                                    overlay_corners, render_board_jpeg)

CB = parse_board_config({"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25})


def _synthetic_checkerboard_jpeg():
    # 9x6 inner corners => 10x7 squares. Draw a clean, well-exposed board with a border.
    sq = 60
    cols_sq, rows_sq = CB.cols + 1, CB.rows + 1
    board = np.zeros((rows_sq * sq, cols_sq * sq), np.uint8)
    for r in range(rows_sq):
        for c in range(cols_sq):
            if (r + c) % 2 == 0:
                board[r*sq:(r+1)*sq, c*sq:(c+1)*sq] = 255
    img = np.full((board.shape[0] + 160, board.shape[1] + 160), 128, np.uint8)
    img[80:80+board.shape[0], 80:80+board.shape[1]] = board
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def test_detect_checkerboard_full():
    gray, corners, n = detect_board(_synthetic_checkerboard_jpeg(), CB)
    assert corners is not None and n == 54
    assert gray.ndim == 2


def test_metrics_pass_verdict():
    from econ_cam.calib_quality import verdict_from_metrics
    gray, corners, _ = detect_board(_synthetic_checkerboard_jpeg(), CB)
    m = quality_metrics(gray, corners, CB)
    assert m["detected"] and abs(m["corner_ratio"] - 1.0) < 1e-6
    assert m["area_frac"] > 0.03 and 40 <= m["roi_mean"] <= 220
    assert verdict_from_metrics(m)["ok"] is True


def test_detect_returns_none_on_blank():
    blank = cv2.imencode(".jpg", np.full((480, 640), 128, np.uint8))[1].tobytes()
    gray, corners, n = detect_board(blank, CB)
    assert corners is None and n == 0
    assert quality_metrics(gray, corners, CB)["detected"] is False


def test_pose_descriptor_center_and_overlay():
    gray, corners, _ = detect_board(_synthetic_checkerboard_jpeg(), CB)
    d = pose_descriptor(gray, corners)
    assert 0.3 < d["center_x"] < 0.7 and 0.3 < d["center_y"] < 0.7
    out = overlay_corners(_synthetic_checkerboard_jpeg(), CB, corners)
    assert out[:2] == b"\xff\xd8"   # JPEG SOI marker


def test_charuco_render_and_detect():
    cc = parse_board_config({"board_type": "charuco", "cols": 5, "rows": 7,
                             "square_mm": 30, "marker_mm": 22, "dictionary": "DICT_5X5_100"})
    jpeg = render_board_jpeg(cc)          # rendered charuco board
    gray, corners, n = detect_board(jpeg, cc)
    assert corners is not None and n >= int(cc.expected_corners * 0.5)
