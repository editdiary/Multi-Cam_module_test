"""intrinsic 계산 + undistort 맵 + JPEG 보정 + JSON 저장/로드.
cv2 계산 로직 격리 (opencv-contrib-python + numpy, venv 전용)."""
import json
from dataclasses import dataclass, asdict

import cv2
import numpy as np

from .calib_board import BoardConfig, object_points
from .calib_detect import _charuco_board


@dataclass
class Intrinsics:
    model: str                       # "pinhole" | "fisheye"
    K: list                          # 3x3
    dist: list                       # 계수 벡터
    image_size: tuple               # (w, h)
    rms: float
    per_view_errors: list
    n_images: int
    board: dict
    source_session: str = ""     # 이 intrinsic을 계산한 세션(폴더) 이름 (활성본에 기록)


def _decode_gray(jpeg):
    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)


def correspondences(jpegs, cfg: BoardConfig):
    """저장 프레임에서 (objpoints, imgpoints, image_size, used_idx) 추출."""
    objp_grid = np.array(object_points(cfg), np.float32).reshape(-1, 1, 3)
    objpoints, imgpoints, used = [], [], []
    image_size = None
    charuco_det = (cv2.aruco.CharucoDetector(_charuco_board(cfg))
                   if cfg.board_type == "charuco" else None)
    for i, jpeg in enumerate(jpegs):
        gray = _decode_gray(jpeg)
        if gray is None:
            continue
        h, w = gray.shape
        if cfg.board_type == "checkerboard":
            ok, corners = cv2.findChessboardCornersSB(
                gray, (cfg.cols, cfg.rows), flags=cv2.CALIB_CB_EXHAUSTIVE)
            if not ok or corners is None or len(corners) != cfg.expected_corners:
                continue
            objpoints.append(objp_grid.copy())
            imgpoints.append(corners.astype(np.float32).reshape(-1, 1, 2))
        else:  # charuco: ID 포함 재검출 → matchImagePoints
            ch_c, ch_ids, _, _ = charuco_det.detectBoard(gray)
            if ch_ids is None or len(ch_ids) < 6:
                continue
            op, ip = _charuco_board(cfg).matchImagePoints(ch_c, ch_ids)
            if op is None or len(op) < 6:
                continue
            objpoints.append(op.astype(np.float32).reshape(-1, 1, 3))
            imgpoints.append(ip.astype(np.float32).reshape(-1, 1, 2))
        used.append(i)
        image_size = (w, h)
    return objpoints, imgpoints, image_size, used


def _per_view_errors(objpoints, imgpoints, rvecs, tvecs, K, dist, model):
    errs = []
    for op, ip, rv, tv in zip(objpoints, imgpoints, rvecs, tvecs):
        if model == "fisheye":
            proj, _ = cv2.fisheye.projectPoints(op, rv, tv, K, dist)
        else:
            proj, _ = cv2.projectPoints(op, rv, tv, K, dist)
        proj = proj.reshape(-1, 2)
        errs.append(float(np.sqrt(np.mean(np.sum(
            (proj - ip.reshape(-1, 2)) ** 2, axis=1)))))
    return errs


def build_undistort_maps(intr: Intrinsics, out_size, alpha: float = 0.0):
    """out_size=(w,h) 해상도용 (map1,map2). K를 원본→out_size 비율로 스케일."""
    ow, oh = out_size
    iw, ih = intr.image_size
    sx, sy = ow / iw, oh / ih
    K = np.array(intr.K, np.float64)
    K = K.copy()
    K[0, 0] *= sx; K[0, 2] *= sx      # fx, cx
    K[1, 1] *= sy; K[1, 2] *= sy      # fy, cy
    dist = np.array(intr.dist, np.float64)
    if intr.model == "fisheye":
        D = dist.reshape(-1, 1)[:4]
        newK = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
            K, D, (ow, oh), np.eye(3), balance=1.0 - alpha)
        m1, m2 = cv2.fisheye.initUndistortRectifyMap(
            K, D, np.eye(3), newK, (ow, oh), cv2.CV_16SC2)
    else:
        newK, _ = cv2.getOptimalNewCameraMatrix(K, dist, (ow, oh), alpha, (ow, oh))
        m1, m2 = cv2.initUndistortRectifyMap(
            K, dist, np.eye(3), newK, (ow, oh), cv2.CV_16SC2)
    return m1, m2


def rectify_jpeg(jpeg: bytes, maps) -> bytes:
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jpeg
    out = cv2.remap(img, maps[0], maps[1], cv2.INTER_LINEAR)
    ok, buf = cv2.imencode(".jpg", out)
    return buf.tobytes() if ok else jpeg


def save_intrinsics(path: str, intr: Intrinsics) -> None:
    with open(path, "w") as f:
        json.dump(asdict(intr), f, indent=2)


def load_intrinsics(path: str) -> Intrinsics:
    with open(path) as f:
        d = json.load(f)
    d["image_size"] = tuple(d["image_size"])
    return Intrinsics(**d)


def compute_intrinsics(jpegs, cfg: BoardConfig, model="pinhole") -> Intrinsics:
    objpoints, imgpoints, image_size, _ = correspondences(jpegs, cfg)
    if len(objpoints) < 4:
        raise ValueError(f"보드 검출 프레임 부족: {len(objpoints)}장 (최소 4장)")
    if model == "fisheye":
        K = np.zeros((3, 3))
        D = np.zeros((4, 1))
        flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_FIX_SKEW
        rms, K, D, rvecs, tvecs = cv2.fisheye.calibrate(
            objpoints, imgpoints, image_size, K, D, flags=flags)
        dist = D
    else:
        rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
            objpoints, imgpoints, image_size, None, None)
    errs = _per_view_errors(objpoints, imgpoints, rvecs, tvecs, K, dist, model)
    return Intrinsics(
        model=model,
        K=K.tolist(),
        dist=np.asarray(dist).reshape(-1).tolist(),
        image_size=image_size,
        rms=float(rms),
        per_view_errors=[round(e, 4) for e in errs],
        n_images=len(objpoints),
        board=cfg.to_dict(),
    )
