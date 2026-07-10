import numpy as np
import cv2
import pytest
from econ_cam.calib_board import BoardConfig
from econ_cam import calib_intrinsics as ci


def _render_checkerboard_views(cols, rows, square_px=60, n=12):
    """합성 체커보드 JPEG 목록 생성 (약간의 원근 변형으로 다양한 자세)."""
    W, H = 1280, 720
    inner = np.zeros(((rows + 1) * square_px, (cols + 1) * square_px), np.uint8)
    for i in range(rows + 1):
        for j in range(cols + 1):
            if (i + j) % 2 == 0:
                inner[i*square_px:(i+1)*square_px, j*square_px:(j+1)*square_px] = 255
    bw, bh = inner.shape[1], inner.shape[0]
    jpegs = []
    for k in range(n):
        dx = (k % 4) * 40 - 60
        dy = (k // 4) * 40 - 40
        src = np.float32([[0, 0], [bw, 0], [bw, bh], [0, bh]])
        dst = np.float32([[300 + dx, 150 + dy], [900 + dx + k*3, 160 + dy],
                          [880 + dx, 560 + dy], [320 + dx, 540 + dy - k*2]])
        M = cv2.getPerspectiveTransform(src, dst)
        canvas = np.full((H, W), 128, np.uint8)
        warp = cv2.warpPerspective(inner, M, (W, H), borderValue=128)
        mask = cv2.warpPerspective(np.full_like(inner, 255), M, (W, H))
        canvas[mask > 0] = warp[mask > 0]
        ok, buf = cv2.imencode(".jpg", canvas)
        jpegs.append(buf.tobytes())
    return jpegs


def test_compute_intrinsics_pinhole_checkerboard():
    cfg = BoardConfig(board_type="checkerboard", cols=9, rows=6, square_mm=25.0)
    jpegs = _render_checkerboard_views(9, 6)
    intr = ci.compute_intrinsics(jpegs, cfg, model="pinhole")
    assert intr.model == "pinhole"
    assert len(intr.K) == 3 and len(intr.K[0]) == 3
    assert intr.K[0][0] > 0 and intr.K[1][1] > 0          # fx, fy 양수
    assert intr.image_size == (1280, 720)
    assert intr.rms < 1.0                                  # 합성 데이터 → 낮은 RMS
    assert intr.n_images >= 8
    assert len(intr.per_view_errors) == intr.n_images


def test_compute_intrinsics_too_few_images():
    cfg = BoardConfig(board_type="checkerboard", cols=9, rows=6, square_mm=25.0)
    with pytest.raises(ValueError):
        ci.compute_intrinsics([b"not-an-image"], cfg, model="pinhole")


def test_save_load_roundtrip(tmp_path):
    intr = ci.Intrinsics(model="pinhole", K=[[1000.0,0,640.0],[0,1000.0,360.0],[0,0,1.0]],
                         dist=[0.1,-0.2,0.0,0.0,0.05], image_size=(1280,720),
                         rms=0.42, per_view_errors=[0.4,0.44], n_images=2,
                         board={"board_type":"checkerboard","cols":9,"rows":6,
                                "square_mm":25.0,"marker_mm":0.0,"dictionary":"DICT_5X5_100"})
    p = tmp_path / "intrinsics_pinhole.json"
    ci.save_intrinsics(str(p), intr)
    back = ci.load_intrinsics(str(p))
    assert back.model == "pinhole"
    assert back.K == intr.K
    assert back.dist == intr.dist
    assert back.image_size == (1280, 720)   # JSON 라운드트립 후에도 튜플
    assert back.rms == 0.42


def test_build_maps_and_rectify_pinhole():
    cfg = BoardConfig(board_type="checkerboard", cols=9, rows=6, square_mm=25.0)
    jpegs = _render_checkerboard_views(9, 6)
    intr = ci.compute_intrinsics(jpegs, cfg, model="pinhole")
    maps = ci.build_undistort_maps(intr, out_size=(640, 360))
    assert maps[0].shape[:2] == (360, 640)      # (h, w)
    out = ci.rectify_jpeg(jpegs[0], maps)
    img = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
    assert img is not None and img.shape[1] == 640 and img.shape[0] == 360


def test_build_maps_fisheye():
    cfg = BoardConfig(board_type="checkerboard", cols=9, rows=6, square_mm=25.0)
    jpegs = _render_checkerboard_views(9, 6)
    intr = ci.compute_intrinsics(jpegs, cfg, model="fisheye")
    maps = ci.build_undistort_maps(intr, out_size=(640, 360))
    assert maps[0].shape[:2] == (360, 640)


def test_rectify_jpeg_bad_input_returns_original():
    cfg = BoardConfig(board_type="checkerboard", cols=9, rows=6, square_mm=25.0)
    jpegs = _render_checkerboard_views(9, 6)
    intr = ci.compute_intrinsics(jpegs, cfg, model="pinhole")
    maps = ci.build_undistort_maps(intr, out_size=(640, 360))
    assert ci.rectify_jpeg(b"garbage", maps) == b"garbage"
