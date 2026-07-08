"""cv2-based board detection, quality metrics, pose descriptor, corner overlay,
and board rendering. Requires opencv-contrib-python + numpy (venv)."""
import cv2
import numpy as np
from .calib_board import BoardConfig


def _decode_gray(jpeg: bytes):
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("JPEG decode failed")
    return img


def _charuco_board(cfg: BoardConfig):
    dic = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, cfg.dictionary))
    return cv2.aruco.CharucoBoard((cfg.cols, cfg.rows), cfg.square_mm, cfg.marker_mm, dic)


def detect_board(jpeg: bytes, cfg: BoardConfig):
    """-> (gray, corners Nx2 float32 | None, count)."""
    gray = _decode_gray(jpeg)
    if cfg.board_type == "checkerboard":
        ok, corners = cv2.findChessboardCornersSB(
            gray, (cfg.cols, cfg.rows), flags=cv2.CALIB_CB_EXHAUSTIVE)
        if ok:
            pts = corners.reshape(-1, 2).astype(np.float32)
            return gray, pts, len(pts)
        return gray, None, 0
    detector = cv2.aruco.CharucoDetector(_charuco_board(cfg))
    ch_corners, ch_ids, _, _ = detector.detectBoard(gray)
    if ch_ids is not None and len(ch_ids) > 0:
        pts = ch_corners.reshape(-1, 2).astype(np.float32)
        return gray, pts, len(pts)
    return gray, None, 0


def quality_metrics(gray, corners, cfg: BoardConfig) -> dict:
    h, w = gray.shape
    detected = corners is not None
    m = {"board_type": cfg.board_type, "detected": detected,
         "corner_ratio": (len(corners) / cfg.expected_corners) if detected else 0.0}
    if not detected:
        m.update(sharpness=0.0, roi_mean=0.0, contrast=0.0,
                 min_edge_frac=0.0, area_frac=0.0)
        return m
    xs, ys = corners[:, 0], corners[:, 1]
    x0, y0 = max(int(xs.min()), 0), max(int(ys.min()), 0)
    x1, y1 = min(int(xs.max()) + 1, w), min(int(ys.max()) + 1, h)
    roi = gray[y0:y1, x0:x1]
    m["sharpness"] = float(cv2.Laplacian(roi, cv2.CV_64F).var())
    m["roi_mean"] = float(roi.mean())
    p5, p95 = np.percentile(roi, (5, 95))
    m["contrast"] = float(p95 - p5)   # dynamic range; low => washed-out/glare/too-dark
    m["min_edge_frac"] = float(
        min(xs.min(), w - xs.max(), ys.min(), h - ys.max()) / min(w, h))
    hull = cv2.convexHull(corners)
    m["area_frac"] = float(cv2.contourArea(hull) / (w * h))
    return m


def pose_descriptor(gray, corners) -> dict:
    h, w = gray.shape
    hull = cv2.convexHull(corners)
    return {"center_x": float(corners[:, 0].mean() / w),
            "center_y": float(corners[:, 1].mean() / h),
            "area_frac": float(cv2.contourArea(hull) / (w * h))}


def overlay_corners(jpeg: bytes, cfg: BoardConfig, corners) -> bytes:
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if corners is not None:
        if cfg.board_type == "checkerboard":
            cv2.drawChessboardCorners(
                img, (cfg.cols, cfg.rows), corners.reshape(-1, 1, 2), True)
        else:
            for p in corners:
                cv2.circle(img, (int(p[0]), int(p[1])), 6, (0, 255, 0), 2)
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def render_board_jpeg(cfg: BoardConfig, px: int = 900) -> bytes:
    """Render a printable board (checkerboard or charuco) as JPEG bytes."""
    if cfg.board_type == "charuco":
        img = _charuco_board(cfg).generateImage((px, int(px * cfg.rows / cfg.cols)))
    else:
        cols_sq, rows_sq = cfg.cols + 1, cfg.rows + 1
        sq = px // cols_sq
        board = np.zeros((rows_sq * sq, cols_sq * sq), np.uint8)
        for r in range(rows_sq):
            for c in range(cols_sq):
                if (r + c) % 2 == 0:
                    board[r*sq:(r+1)*sq, c*sq:(c+1)*sq] = 255
        img = cv2.copyMakeBorder(board, sq, sq, sq, sq, cv2.BORDER_CONSTANT, value=128)
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()
