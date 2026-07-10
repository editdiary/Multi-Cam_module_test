# Mode 4 — 보정(Rectification) 확인 모드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **실행 시 첫 단계:** 이 계획을 저장소 규칙 위치로 복사한다 →
> `docs/superpowers/plans/2026-07-09-rectify-mode.md`. (현재는 plan-mode 제약으로 임시 위치에 있음.)
> **Git:** CLAUDE.md 규칙에 따라 새 브랜치(`feat/rectify-mode` 등)에서 작업하고 **커밋까지만** 한다.
> `develop`/`main` merge·push는 사용자가 직접 한다.

**Goal:** Mode 3가 수집한 캘리브레이션 이미지 폴더로 **실제 intrinsic(K·왜곡계수)을 계산**하고, 단일/다중 카메라 라이브 영상을 **실시간으로 왜곡 보정**해 "좌: 광각 원본 / 우: 평평하게 펴진 보정" 형태로 시각 검증하는 새 모드(Mode 4)를 추가한다.

**Architecture:** 순수 로직(오브젝트 포인트 격자)은 `calib_board.py`에 추가, cv2 계산(코너 대응·`calibrateCamera`/`fisheye.calibrate`·undistort 맵·`remap`·JSON 저장/로드)은 새 `calib_intrinsics.py`에 격리한다. 라이브 보정은 새 GStreamer 파이프라인 없이 기존 `Camera.latest_jpeg()`/`SyncSession.latest_jpeg(dev)`의 JPEG을 디코드→`cv2.remap`→재인코드하는 MJPEG 라우트로 붙인다. 프런트는 기존 탭/서브탭·그리드·MJPEG `<img src>` 패턴을 그대로 재사용한다.

**Tech Stack:** Python 3.10 (venv, `--system-site-packages`), Flask 3.1, GStreamer(`gi`), **opencv-contrib-python 4.8.1.78**, numpy 1.24.4, pytest. 프런트는 무프레임워크(순수 DOM + class 토글).

## Global Constraints

- 새 pip 의존성 **추가 금지**. cv2/numpy는 이미 venv에 있음(`requirements.txt` 그대로). 호스트 apt 무변경.
- cv2 사용은 **계산·검출·보정 로직에 한정**(`calib_intrinsics.py`, 기존 `calib_detect.py`). 캡처/스트리밍 파이프라인은 GStreamer JPEG 그대로 유지.
- 순수 로직(격자·저장 스키마)은 하드웨어 없이 pytest로 검증. cv2 로직은 **합성(synthetic) 이미지**로 실제 cv2 실행 테스트(기존 `tests/test_calib_detect.py` 컨벤션). 하드웨어(`/dev/videoN`) 의존 테스트만 `skipif`.
- 파일은 관심사별로 작게: 순수=`calib_board.py`, cv2 계산=`calib_intrinsics.py`, Flask=`app.py`.
- `captures/` 는 **절대 blanket-delete 금지**(gitignore, 복구 불가). 새 산출물만 추가한다.
- 왜곡 모델은 **UI에서 선택**(기본 `pinhole`, 옵션 `fisheye`) — 두 경로 모두 구현.
- 보드 종류 **둘 다 지원**: `checkerboard`(격자 순서 대응) + `charuco`(ID 필요 → `CharucoBoard.matchImagePoints`).
- intrinsic 저장은 **카메라별**. 세션 폴더에 모델별 캐시(`intrinsics_<model>.json`)를 두고 **있으면 재사용, 없으면 새로 계산**(force 옵션으로 재계산). 활성본은 `captures/calib/intrinsics/video<dev>.json`.
- 다중 라이브 레이아웃 = **보정 그리드 + 원본/보정 토글**(토글은 클라이언트에서 `img.src`를 원본 스트림↔보정 스트림으로 교체).

## 확인된 사실 (탐색·실측)

- **디스크 레이아웃(Mode 3 intrinsic):** `captures/calib/intrinsic/<YYYYMMDD_HHMMSS>/` 안에
  `board_config.json`(예: `{"board_type":"checkerboard","cols":10,"rows":7,"square_mm":25.0,"marker_mm":0.0,"dictionary":"DICT_5X5_100"}`),
  `report.json`(카메라별 프레임 목록, `cameras` 키 = dev), `video<dev>/frame_000.jpg …`. intrinsic 세션은 단일 카메라.
- **`report.json`은 코너 좌표를 저장하지 않는다** → 계산 시 저장된 JPEG에서 **코너를 재검출**해야 한다.
- **기존 검출기(`calib_detect.detect_board`)는 charuco의 ID를 버린다.** calibrate에는 ID가 필요하므로 `calib_intrinsics.py`에서 charuco를 **재검출(ID 포함)** 한다. checkerboard는 `findChessboardCornersSB((cols,rows))` 격자 순서와 `object_points` 순서를 맞춘다.
- **OpenCV 4.8.1 실측 확인:** `calibrateCamera`, `getOptimalNewCameraMatrix`, `initUndistortRectifyMap`, `findChessboardCornersSB`, `fisheye.calibrate`, `fisheye.initUndistortRectifyMap`, `fisheye.estimateNewCameraMatrixForUndistortRectify`, `aruco.CharucoDetector`, `CharucoBoard.matchImagePoints(detectedCorners, detectedIds) -> objPoints, imgPoints`, `projectPoints`, `fisheye.projectPoints` 모두 사용 가능. `fisheye.CALIB_RECOMPUTE_EXTRINSIC=2`, `fisheye.CALIB_FIX_SKEW=8`. `findChessboardCornersSB` 반환은 `(bool, corners(N,1,2)float32)`.
- **해상도 독립성:** 왜곡계수는 정규화 좌표 기반이라 해상도 불변. K의 `fx,fy,cx,cy`만 대상 해상도 비율로 스케일하면 프리뷰(640×360)용 undistort 맵을 만들 수 있다(프리뷰 상수: `gst_pipeline.PREVIEW_WIDTH=640`, `PREVIEW_HEIGHT=360`).
- **스트림 재사용:** 단일 = `Camera.latest_jpeg()`(`get_or_start_stream(dev)`), 다중 = `SyncSession.latest_jpeg(dev)`. 원본 스트림 라우트(`/api/stream/<dev>/mjpeg`, `/api/sync/stream/<dev>`)는 그대로 두고 보정 스트림 라우트만 신설.
- **성능:** 640×360 JPEG 디코드→`remap`(사전계산 LUT)→재인코드는 Jetson CPU에서 카메라당 수 ms. 4대 × ~15fps 허용 범위. (원본 파이프라인은 GPU JPEG, 보정만 CPU.)

## File Structure

```
econ_cam/
  calib_board.py        # (수정) object_points(cfg) 순수 함수 추가
  calib_intrinsics.py   # (신규, cv2) 대응·calibrate·undistort맵·remap·JSON 저장/로드
  app.py                # (수정) /api/rectify/* 라우트 + state["rectify"]
  templates/index.html  # (수정) rectify 탭 + 섹션(서브탭 single/multi)
  static/app.js         # (수정) startRectify/stopRectify/compute/스트림/토글
  static/style.css      # (수정) .grid.pair 2열 레이아웃
tests/
  test_calib_board.py       # (수정/신규) object_points 격자 검증
  test_calib_intrinsics.py  # (신규) 합성 이미지 calibrate/undistort/저장 검증
  test_app.py               # (수정) rectify 라우트(monkeypatch)
  test_frontend.py          # (수정) 새 탭 라벨 검증
docs/
  USAGE.md                  # (수정) Mode 4 사용법
captures/calib/intrinsics/  # (런타임 생성) video<dev>.json 활성 intrinsic
```

---

### Task 1: `object_points` 순수 격자 함수 (calib_board.py)

**Files:**
- Modify: `econ_cam/calib_board.py`
- Test: `tests/test_calib_board.py`

**Interfaces:**
- Consumes: 기존 `BoardConfig`(`cols`,`rows`,`square_mm`).
- Produces: `object_points(cfg: BoardConfig) -> list[tuple[float, float, float]]` — checkerboard 내부 코너의 3D 좌표(z=0), `findChessboardCornersSB((cols,rows))` 반환 순서(행 우선: 각 행에 cols개, rows개 행)와 동일. charuco는 이 함수를 쓰지 않는다(objPoints는 `matchImagePoints`가 제공).

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_calib_board.py` 에 추가(파일 없으면 생성, 상단 `from econ_cam.calib_board import BoardConfig, object_points`).

```python
def test_object_points_checkerboard_grid():
    cfg = BoardConfig(board_type="checkerboard", cols=3, rows=2, square_mm=25.0)
    pts = object_points(cfg)
    # 3열 x 2행 = 6개, 행 우선 순서
    assert pts == [
        (0.0, 0.0, 0.0), (25.0, 0.0, 0.0), (50.0, 0.0, 0.0),
        (0.0, 25.0, 0.0), (25.0, 25.0, 0.0), (50.0, 25.0, 0.0),
    ]

def test_object_points_count_matches_expected_corners():
    cfg = BoardConfig(board_type="checkerboard", cols=10, rows=7, square_mm=20.0)
    assert len(object_points(cfg)) == cfg.expected_corners  # 70
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_calib_board.py -v`  Expected: FAIL (`ImportError: cannot import name 'object_points'`).

- [ ] **Step 3: 최소 구현** — `calib_board.py` 하단(순수, cv2/numpy 없음)에 추가:

```python
def object_points(cfg: BoardConfig) -> list[tuple[float, float, float]]:
    """체커보드 내부 코너의 3D 좌표(z=0). findChessboardCornersSB((cols,rows)) 순서와 동일:
    각 행마다 cols개, 총 rows개 행(행 우선)."""
    s = cfg.square_mm
    return [
        (col * s, row * s, 0.0)
        for row in range(cfg.rows)
        for col in range(cfg.cols)
    ]
```

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests/test_calib_board.py -v`  Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/calib_board.py tests/test_calib_board.py
git commit -m "feat(rectify): add object_points grid helper for intrinsic calibration"
```

---

### Task 2: intrinsic 계산 — 대응 + calibrate (calib_intrinsics.py)

**Files:**
- Create: `econ_cam/calib_intrinsics.py`
- Test: `tests/test_calib_intrinsics.py`

**Interfaces:**
- Consumes: `BoardConfig`, `object_points`(Task 1), `calib_detect._charuco_board`(charuco 재검출용, 이미 존재).
- Produces:
  - `@dataclass Intrinsics`: `model: str`("pinhole"|"fisheye"), `K: list[list[float]]`(3×3), `dist: list[float]`, `image_size: tuple[int,int]`(w,h), `rms: float`, `per_view_errors: list[float]`, `n_images: int`, `board: dict`.
  - `correspondences(jpegs: list[bytes], cfg: BoardConfig) -> tuple[list, list, tuple[int,int], list[int]]` → `(objpoints, imgpoints, image_size, used_idx)`; 각 원소는 numpy 배열(objpoints: (N,1,3)float32, imgpoints: (N,1,2)float32).
  - `compute_intrinsics(jpegs: list[bytes], cfg: BoardConfig, model: str = "pinhole") -> Intrinsics`. 검출 성공 프레임이 부족하면(`< 4`) `ValueError`.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_calib_intrinsics.py` 생성. 합성 체커보드를 여러 자세로 렌더해 왜곡을 살짝 준 뒤 계산이 수렴하는지 확인한다.

```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_calib_intrinsics.py -v`  Expected: FAIL (module not found).

- [ ] **Step 3: 최소 구현** — `econ_cam/calib_intrinsics.py` 생성:

```python
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
```

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests/test_calib_intrinsics.py -v`  Expected: PASS(두 테스트). RMS가 <1.0로 수렴.

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/calib_intrinsics.py tests/test_calib_intrinsics.py
git commit -m "feat(rectify): compute pinhole/fisheye intrinsics from stored board images"
```

---

### Task 3: intrinsics JSON 저장/로드 (calib_intrinsics.py)

**Files:**
- Modify: `econ_cam/calib_intrinsics.py`
- Test: `tests/test_calib_intrinsics.py`

**Interfaces:**
- Produces: `save_intrinsics(path: str, intr: Intrinsics) -> None`; `load_intrinsics(path: str) -> Intrinsics`. JSON은 프로젝트 관례(사람이 읽기 쉬움)대로 리스트 형태로 K/dist 저장.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_calib_intrinsics.py` 에 추가:

```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_calib_intrinsics.py::test_save_load_roundtrip -v`  Expected: FAIL (`AttributeError: save_intrinsics`).

- [ ] **Step 3: 최소 구현** — `calib_intrinsics.py` 에 추가:

```python
def save_intrinsics(path: str, intr: Intrinsics) -> None:
    with open(path, "w") as f:
        json.dump(asdict(intr), f, indent=2)


def load_intrinsics(path: str) -> Intrinsics:
    with open(path) as f:
        d = json.load(f)
    d["image_size"] = tuple(d["image_size"])
    return Intrinsics(**d)
```

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests/test_calib_intrinsics.py -v`  Expected: PASS(3 tests).

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/calib_intrinsics.py tests/test_calib_intrinsics.py
git commit -m "feat(rectify): JSON save/load for intrinsics"
```

---

### Task 4: undistort 맵 + JPEG 보정 (calib_intrinsics.py)

**Files:**
- Modify: `econ_cam/calib_intrinsics.py`
- Test: `tests/test_calib_intrinsics.py`

**Interfaces:**
- Produces:
  - `build_undistort_maps(intr: Intrinsics, out_size: tuple[int,int], alpha: float = 0.0) -> tuple[np.ndarray, np.ndarray]` — `out_size=(w,h)`. K를 `intr.image_size`→`out_size` 비율로 스케일한 뒤, pinhole은 `getOptimalNewCameraMatrix`+`initUndistortRectifyMap`, fisheye는 `estimateNewCameraMatrixForUndistortRectify`+`fisheye.initUndistortRectifyMap`으로 `(map1, map2)`를 만든다.
  - `rectify_jpeg(jpeg: bytes, maps: tuple[np.ndarray,np.ndarray]) -> bytes` — 컬러 디코드→`cv2.remap`→JPEG 재인코드. 디코드 실패 시 원본 반환.

- [ ] **Step 1: 실패 테스트 작성** — 추가:

```python
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
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_calib_intrinsics.py -k "maps or rectify" -v`  Expected: FAIL.

- [ ] **Step 3: 최소 구현** — `calib_intrinsics.py` 에 추가:

```python
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
```

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests/test_calib_intrinsics.py -v`  Expected: PASS(6 tests).

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/calib_intrinsics.py tests/test_calib_intrinsics.py
git commit -m "feat(rectify): undistort map builder + per-frame JPEG rectification"
```

---

### Task 5: 계산·활성화 API 라우트 (app.py)

**Files:**
- Modify: `econ_cam/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `calib_intrinsics`(Task 2–4), `calib_board.parse_board_config`, 기존 `CALIB_DIR`, `state`.
- Produces:
  - `POST /api/rectify/compute` — body `{"session": "<name>", "sub_mode": "intrinsic", "model": "pinhole"|"fisheye", "force": bool}`. 세션 폴더에서 dev·프레임을 읽어 계산. **캐시 재사용:** 세션에 `intrinsics_<model>.json`이 있고 `force`가 아니면 로드. 계산 후 세션 캐시 + 활성본(`captures/calib/intrinsics/video<dev>.json`) 저장. 응답 `{"ok":True,"dev":int,"model","rms","per_view_errors","n_images","image_size","cached":bool}`.
  - `GET /api/rectify/intrinsics/<int:dev>` — 활성 intrinsic 요약(`{"has":bool,"model","rms","image_size","board"}`), 없으면 `has:false`.
  - 모듈 상단 상수: `INTR_DIR = os.path.join(CALIB_DIR, "intrinsics")`.
- 헬퍼(app.py 내부): `_session_dir(sub_mode, name)`, `_session_dev(session_dir)`(report.json `cameras` 첫 키; 없으면 `video<dev>/` 폴더명에서 추출), `_load_session_jpegs(session_dir, dev)`(정렬된 `video<dev>/frame_*.jpg` 바이트 목록), `_active_intr_path(dev)`.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_app.py` 에 추가. 실제 계산은 무겁고 하드웨어 무관이므로 `calib_intrinsics.compute_intrinsics`를 monkeypatch로 가짜 `Intrinsics` 반환하도록 하고, 세션 폴더는 `tmp_path`로 만들어 `CALIB_DIR`을 패치한다.

```python
import os, json
import econ_cam.app as app_module
from econ_cam import calib_intrinsics as ci

def _make_session(tmp_path):
    sess = tmp_path / "intrinsic" / "20260709_000000"
    (sess / "video0").mkdir(parents=True)
    (sess / "board_config.json").write_text(json.dumps(
        {"board_type":"checkerboard","cols":9,"rows":6,"square_mm":25.0,
         "marker_mm":0.0,"dictionary":"DICT_5X5_100"}))
    (sess / "report.json").write_text(json.dumps({"cameras": {"0": []}}))
    for i in range(2):
        (sess / "video0" / f"frame_{i:03d}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    return sess

def test_rectify_compute(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "INTR_DIR", str(tmp_path / "intrinsics"))
    _make_session(tmp_path)
    fake = ci.Intrinsics(model="pinhole", K=[[1,0,0],[0,1,0],[0,0,1]], dist=[0]*5,
                         image_size=(1280,720), rms=0.3, per_view_errors=[0.3,0.3],
                         n_images=2, board={"board_type":"checkerboard"})
    monkeypatch.setattr(app_module.calib_intrinsics, "compute_intrinsics",
                        lambda *a, **k: fake)
    client = app_module.create_app().test_client()
    r = client.post("/api/rectify/compute",
                    json={"session":"20260709_000000","sub_mode":"intrinsic","model":"pinhole"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] and body["dev"] == 0 and body["rms"] == 0.3 and body["cached"] is False
    # 활성본이 기록됨
    assert os.path.exists(str(tmp_path / "intrinsics" / "video0.json"))
    # 두 번째 호출은 캐시 재사용
    r2 = client.post("/api/rectify/compute",
                     json={"session":"20260709_000000","sub_mode":"intrinsic","model":"pinhole"})
    assert r2.get_json()["cached"] is True

def test_rectify_intrinsics_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "INTR_DIR", str(tmp_path / "intrinsics"))
    client = app_module.create_app().test_client()
    assert client.get("/api/rectify/intrinsics/3").get_json()["has"] is False
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_app.py -k rectify -v`  Expected: FAIL (404 / 라우트 없음).

- [ ] **Step 3: 최소 구현** — `app.py`:
  - 상단 import에 `from econ_cam import calib_intrinsics` (또는 기존 import 스타일에 맞춰 `from . import calib_intrinsics`), `from econ_cam.calib_board import parse_board_config` 재사용.
  - `CALIB_DIR` 정의 직후 `INTR_DIR = os.path.join(CALIB_DIR, "intrinsics")` 추가.
  - `create_app` 내부에 헬퍼 + 라우트 추가:

```python
def _session_dir(sub_mode, name):
    return os.path.join(CALIB_DIR, sub_mode, name)

def _session_dev(session_dir):
    rp = os.path.join(session_dir, "report.json")
    if os.path.exists(rp):
        with open(rp) as f:
            cams = json.load(f).get("cameras", {})
        if cams:
            return int(sorted(cams.keys())[0])
    for n in sorted(os.listdir(session_dir)):
        if n.startswith("video") and os.path.isdir(os.path.join(session_dir, n)):
            return int(n[len("video"):])
    raise ValueError("세션에서 카메라를 찾을 수 없음")

def _load_session_jpegs(session_dir, dev):
    d = os.path.join(session_dir, f"video{dev}")
    files = sorted(f for f in os.listdir(d) if f.endswith(".jpg"))
    out = []
    for f in files:
        with open(os.path.join(d, f), "rb") as fh:
            out.append(fh.read())
    return out

def _active_intr_path(dev):
    return os.path.join(INTR_DIR, f"video{dev}.json")

@app.route("/api/rectify/compute", methods=["POST"])
def api_rectify_compute():
    body = request.get_json(force=True)
    sub_mode = body.get("sub_mode", "intrinsic")
    name = body["session"]
    model = body.get("model", "pinhole")
    force = bool(body.get("force"))
    session_dir = _session_dir(sub_mode, name)
    if not os.path.isdir(session_dir):
        return jsonify({"ok": False, "error": "세션 없음"}), 404
    dev = _session_dev(session_dir)
    cache_path = os.path.join(session_dir, f"intrinsics_{model}.json")
    cached = False
    if os.path.exists(cache_path) and not force:
        intr = calib_intrinsics.load_intrinsics(cache_path)
        cached = True
    else:
        with open(os.path.join(session_dir, "board_config.json")) as f:
            cfg = parse_board_config(json.load(f))
        jpegs = _load_session_jpegs(session_dir, dev)
        try:
            intr = calib_intrinsics.compute_intrinsics(jpegs, cfg, model=model)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        calib_intrinsics.save_intrinsics(cache_path, intr)
    os.makedirs(INTR_DIR, exist_ok=True)
    calib_intrinsics.save_intrinsics(_active_intr_path(dev), intr)
    with state["lock"]:
        state["rectify"]["maps"].pop(dev, None)   # 재계산 시 맵 무효화
    return jsonify({"ok": True, "dev": dev, "model": intr.model, "rms": intr.rms,
                    "per_view_errors": intr.per_view_errors, "n_images": intr.n_images,
                    "image_size": list(intr.image_size), "cached": cached})

@app.route("/api/rectify/intrinsics/<int:dev>")
def api_rectify_intrinsics(dev):
    p = _active_intr_path(dev)
    if not os.path.exists(p):
        return jsonify({"has": False})
    intr = calib_intrinsics.load_intrinsics(p)
    return jsonify({"has": True, "model": intr.model, "rms": intr.rms,
                    "image_size": list(intr.image_size), "board": intr.board})
```
  - `state` dict 초기화에 `"rectify": {"maps": {}, "session": None}` 추가(Task 6에서도 사용).

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests/test_app.py -k rectify -v`  Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/app.py tests/test_app.py
git commit -m "feat(rectify): /api/rectify/compute (cache-or-compute) + intrinsics query routes"
```

---

### Task 6: 보정 라이브 스트림 라우트 (app.py)

**Files:**
- Modify: `econ_cam/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `state["rectify"]["maps"]`, `get_or_start_stream(dev)`(단일), `state["sync_session"]`(다중), `calib_intrinsics.build_undistort_maps`/`rectify_jpeg`, `_active_intr_path`, `gst_pipeline.PREVIEW_WIDTH/HEIGHT`.
- Produces:
  - 헬퍼 `_get_maps(dev)` — dev의 활성 intrinsic을 로드해 프리뷰 해상도(`PREVIEW_WIDTH×PREVIEW_HEIGHT`)용 맵을 만들어 `state["rectify"]["maps"]`에 캐시. intrinsic 없으면 `None`.
  - `GET /api/rectify/stream/<int:dev>` — 단일 카메라 보정 MJPEG(`get_or_start_stream(dev).latest_jpeg()` → `rectify_jpeg`). 맵 없으면 404.
  - `GET /api/rectify/sync/stream/<int:dev>` — 다중(SyncSession) 보정 MJPEG(`sess.latest_jpeg(dev)` → `rectify_jpeg`). 세션/맵 없으면 404.
  - (원본 스트림은 기존 `/api/stream/<dev>/mjpeg`·`/api/sync/stream/<dev>` 재사용 — 신설 안 함.)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_app.py` 에 추가. intrinsic 활성본을 tmp에 저장하고, 맵 생성이 되는지(스트림 라우트가 404가 아닌 200으로 열리는지)만 확인(프레임 내용은 하드웨어 필요라 미검증). 활성본 없으면 404 확인.

```python
def test_rectify_stream_404_without_intrinsics(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "INTR_DIR", str(tmp_path / "intrinsics"))
    client = app_module.create_app().test_client()
    assert client.get("/api/rectify/stream/0").status_code == 404

def test_rectify_stream_opens_with_intrinsics(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "INTR_DIR", str(tmp_path / "intrinsics"))
    os.makedirs(str(tmp_path / "intrinsics"))
    # 실제 계산 산출 intrinsic 저장 (합성)
    from tests.test_calib_intrinsics import _render_checkerboard_views
    from econ_cam.calib_board import BoardConfig
    cfg = BoardConfig(board_type="checkerboard", cols=9, rows=6, square_mm=25.0)
    intr = ci.compute_intrinsics(_render_checkerboard_views(9,6), cfg, model="pinhole")
    ci.save_intrinsics(str(tmp_path / "intrinsics" / "video0.json"), intr)
    # 단일 스트림 카메라를 가짜로 대체 (한 프레임만 반환)
    class _FakeCam:
        def latest_jpeg(self):
            import cv2, numpy as np
            ok, buf = cv2.imencode(".jpg", np.zeros((360,640,3), np.uint8))
            return buf.tobytes()
    monkeypatch.setattr(app_module, "get_or_start_stream", lambda dev: _FakeCam(),
                        raising=False)
    client = app_module.create_app().test_client()
    # get_or_start_stream은 create_app 내부 클로저이므로, 아래 Step 3에서 _get_maps가
    # intrinsic 유무만으로 200/404를 가르도록 구현한다(맵 생성 성공 → 200).
    r = client.get("/api/rectify/stream/0")
    assert r.status_code == 200
```

> 참고: `get_or_start_stream`은 `create_app` 내부 클로저라 monkeypatch가 어려울 수 있다. 스트림 라우트의 **200/404 분기는 `_get_maps(dev)`(활성 intrinsic 유무)만으로 결정**하고, 프레임 생성기는 지연(lazy) 실행되므로 테스트 클라이언트가 본문을 소비하지 않으면 카메라 접근이 일어나지 않는다. 따라서 위 `_FakeCam` 패치가 필요 없으면 제거해도 된다(핵심 단언은 상태코드).

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_app.py -k rectify_stream -v`  Expected: FAIL.

- [ ] **Step 3: 최소 구현** — `app.py`(기존 `api_stream`/`api_sync_stream` 옆). `PREVIEW_WIDTH/HEIGHT`는 `from econ_cam.gst_pipeline import PREVIEW_WIDTH, PREVIEW_HEIGHT` 또는 기존 import 재사용:

```python
def _get_maps(dev):
    with state["lock"]:
        m = state["rectify"]["maps"].get(dev)
    if m is not None:
        return m
    p = _active_intr_path(dev)
    if not os.path.exists(p):
        return None
    intr = calib_intrinsics.load_intrinsics(p)
    maps = calib_intrinsics.build_undistort_maps(
        intr, (PREVIEW_WIDTH, PREVIEW_HEIGHT))
    with state["lock"]:
        state["rectify"]["maps"][dev] = maps
    return maps

@app.route("/api/rectify/stream/<int:dev>")
def api_rectify_stream(dev):
    maps = _get_maps(dev)
    if maps is None:
        return ("intrinsic 없음", 404)
    with state["lock"]:
        cam = get_or_start_stream(dev)
    def gen():
        while state["streams"].get(dev) is cam:
            jpeg = cam.latest_jpeg()
            if jpeg is None:
                continue
            out = calib_intrinsics.rectify_jpeg(jpeg, maps)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + out + b"\r\n")
            time.sleep(1 / 15)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/rectify/sync/stream/<int:dev>")
def api_rectify_sync_stream(dev):
    maps = _get_maps(dev)
    sess = state["sync_session"]
    if maps is None or sess is None:
        return ("", 404)
    def gen():
        last = None
        while state["sync_session"] is sess:
            jpeg = sess.latest_jpeg(dev)
            if jpeg is not None and jpeg is not last:
                last = jpeg
                out = calib_intrinsics.rectify_jpeg(jpeg, maps)
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + out + b"\r\n")
            time.sleep(0.02)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")
```

> 다중 라이브 시작/정지는 **기존 `/api/sync/start`·`/api/sync/stop`을 재사용**한다(프런트가 호출). 별도 `/api/rectify/multi/*` 라우트는 만들지 않는다 — 원본 그리드(`/api/sync/stream/<dev>`)와 보정 그리드(`/api/rectify/sync/stream/<dev>`)가 같은 SyncSession을 공유한다.

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests/test_app.py -k rectify -v`  Expected: PASS. 전체: `.venv/bin/python -m pytest -q` 로 회귀 없음 확인.

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/app.py tests/test_app.py
git commit -m "feat(rectify): live rectified MJPEG stream routes (single + sync)"
```

---

### Task 7: 프런트엔드 — 탭·서브탭·2열 뷰·토글 (index.html / app.js / style.css)

**Files:**
- Modify: `econ_cam/templates/index.html`
- Modify: `econ_cam/static/app.js`
- Modify: `econ_cam/static/style.css`
- Test: `tests/test_frontend.py`

**Interfaces:**
- Consumes: `/api/rectify/compute`, `/api/rectify/intrinsics/<dev>`, `/api/rectify/stream/<dev>`, `/api/rectify/sync/stream/<dev>`, 기존 `/api/calib/sessions?sub_mode=intrinsic`, `/api/stream/<dev>/mjpeg`, `/api/sync/start`·`/api/sync/stop`·`/api/sync/stream/<dev>`, `loadCameras()`의 `cameras` 배열.
- Produces: `data-mode="rectify"` 탭 + `<section id="rectify">`; `startRectify()`/`stopRectify()`; `setMode`에 분기 추가.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_frontend.py` 에 새 탭 라벨 단언 추가(기존 테스트 스타일):

```python
def test_index_has_rectify_tab():
    html = create_app().test_client().get("/").get_data(as_text=True)
    assert 'data-mode="rectify"' in html
    assert "보정 확인" in html
```
(파일 상단 import가 없으면 기존 테스트와 동일하게 `from econ_cam.app import create_app` 사용.)

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_frontend.py -v`  Expected: FAIL.

- [ ] **Step 3: 구현**

  **(a) `index.html`** — 탭 nav(line ~19–23)에 버튼 추가:
```html
<button class="tab" data-mode="rectify">보정 확인</button>
```
  `<section id="calib">` 뒤에 새 섹션 추가(구조는 calib 섹션을 축약 참고 — 서브탭 single/multi):
```html
<section id="rectify" class="mode">
  <div class="card">
    <nav class="subtabs">
      <button class="rsubtab active" data-rsub="single">단일 (Intrinsic 계산·보정)</button>
      <button class="rsubtab" data-rsub="multi">다중 (실시간 보정)</button>
    </nav>

    <div id="rectify-single" class="rsubmode active">
      <div class="toolbar">
        <div class="toolbar-left">
          <select id="rect-session"></select>
          <select id="rect-model">
            <option value="pinhole">Pinhole</option>
            <option value="fisheye">Fisheye</option>
          </select>
        </div>
        <div class="actions">
          <button id="rect-compute">Intrinsic 계산</button>
          <label><input type="checkbox" id="rect-force"> 재계산</label>
        </div>
      </div>
      <div id="rect-status" class="status-line">세션을 선택하고 Intrinsic을 계산하세요.</div>
      <div class="grid pair">
        <figure><img id="rect-orig" alt="원본"><figcaption>광각 원본</figcaption></figure>
        <figure><img id="rect-rect" alt="보정"><figcaption>보정(펴짐)</figcaption></figure>
      </div>
    </div>

    <div id="rectify-multi" class="rsubmode">
      <div class="toolbar">
        <div class="toolbar-left"><div id="rect-multi-cams" class="checkboxes"></div></div>
        <div class="actions">
          <button id="rect-multi-start">라이브 시작</button>
          <label>표시:
            <input type="radio" name="rectview" value="rect" checked> 보정
            <input type="radio" name="rectview" value="orig"> 원본
          </label>
        </div>
      </div>
      <div id="rect-multi-status" class="status-line">보정하려면 각 카메라에 활성 intrinsic이 필요합니다.</div>
      <div id="rect-multi-grid" class="grid"></div>
    </div>
  </div>
</section>
```

  **(b) `style.css`** — 2열 고정 레이아웃 추가(기존 `.grid` 아래):
```css
.grid.pair { grid-template-columns: 1fr 1fr; }
.rsubmode { display: none; }
.rsubmode.active { display: block; }
```

  **(c) `app.js`** — 아래를 추가/수정:
  - `setMode`의 `Promise.all([...]).then` 분기에 `if (mode === "rectify") startRectify();` 추가하고, teardown 3곳(`setMode`, `setCalibSub`)의 `Promise.all`에 `stopRectify()` 포함.
  - 전역 `let rectSub = "single";` 추가.
  - 함수 추가:
```js
function stopRectify() {
  ["rect-orig", "rect-rect"].forEach((id) => { const e = document.getElementById(id); if (e) e.src = ""; });
  const g = document.getElementById("rect-multi-grid"); if (g) g.innerHTML = "";
  return jsonPost("/api/sync/stop", {}).catch(() => {});
}

async function startRectify() {
  await populateRectSessions();
  loadRectMultiCams();
  if (rectSub === "single") startRectSingle();
  else startRectMulti();
}

async function populateRectSessions() {
  const list = await api("/api/calib/sessions?sub_mode=intrinsic");
  document.getElementById("rect-session").innerHTML =
    list.map((s) => `<option value="${s.name}">${s.name} (${s.count}장)</option>`).join("");
}

function loadRectMultiCams() {
  document.getElementById("rect-multi-cams").innerHTML = cameras
    .map((c) => `<label><input type="checkbox" value="${c.dev}" checked> ${c.label}</label>`).join("");
}

function setRectSub(sub) {
  rectSub = sub;
  document.querySelectorAll(".rsubtab").forEach((t) => t.classList.toggle("active", t.dataset.rsub === sub));
  document.querySelectorAll(".rsubmode").forEach((s) => s.classList.toggle("active", s.id === `rectify-${sub}`));
  Promise.all([stopRectify()]).then(startRectify);
}

async function computeRectIntrinsics() {
  const session = document.getElementById("rect-session").value;
  const model = document.getElementById("rect-model").value;
  const force = document.getElementById("rect-force").checked;
  if (!session) { toast("세션을 선택하세요"); return; }
  document.getElementById("rect-status").textContent = "계산 중…";
  const r = await jsonPost("/api/rectify/compute", { session, sub_mode: "intrinsic", model, force });
  if (!r.ok) { document.getElementById("rect-status").textContent = "실패: " + (r.error || ""); return; }
  const el = document.getElementById("rect-status");
  el.textContent = `dev ${r.dev} · ${r.model} · RMS ${r.rms.toFixed(3)}px · ${r.n_images}장`
    + (r.cached ? " (캐시)" : "");
  el.className = "status-line " + (r.rms < 1.0 ? "good" : "warn");
  startRectSingle(r.dev);
}

function startRectSingle(dev) {
  // dev 미지정 시 세션명으로부터 알 수 없으므로, compute 응답의 dev를 사용.
  if (dev === undefined) return;   // 계산 전에는 스트림을 켜지 않음
  const t = Date.now();
  document.getElementById("rect-orig").src = `/api/stream/${dev}/mjpeg?t=${t}`;
  document.getElementById("rect-rect").src = `/api/rectify/stream/${dev}?t=${t}`;
}

async function startRectMulti() {
  const devs = [...document.querySelectorAll("#rect-multi-cams input:checked")].map((c) => Number(c.value));
  if (!devs.length) return;
  await jsonPost("/api/sync/start", { devices: devs, sync_mode: 1 });
  renderRectMultiGrid(devs);
}

function currentRectView() {
  const r = document.querySelector('input[name="rectview"]:checked');
  return r ? r.value : "rect";
}

function renderRectMultiGrid(devs) {
  const view = currentRectView();
  const t = Date.now();
  document.getElementById("rect-multi-grid").innerHTML = devs.map((d) => {
    const src = view === "rect" ? `/api/rectify/sync/stream/${d}?t=${t}` : `/api/sync/stream/${d}?t=${t}`;
    return `<figure><img id="rect-m-${d}" src="${src}"><figcaption>video${d} (${view === "rect" ? "보정" : "원본"})</figcaption></figure>`;
  }).join("");
}
```
  - 이벤트 배선(bootstrap 근처, 기존 `.tab` 배선과 같은 스타일):
```js
document.querySelectorAll(".rsubtab").forEach((t) =>
  t.addEventListener("click", () => setRectSub(t.dataset.rsub)));
document.getElementById("rect-compute").addEventListener("click", computeRectIntrinsics);
document.getElementById("rect-multi-start").addEventListener("click", startRectMulti);
document.querySelectorAll('input[name="rectview"]').forEach((r) =>
  r.addEventListener("change", () => {
    const devs = [...document.querySelectorAll("#rect-multi-cams input:checked")].map((c) => Number(c.value));
    renderRectMultiGrid(devs);   // 토글: img.src만 원본↔보정으로 교체
  }));
```

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests/test_frontend.py -v`  Expected: PASS. 그리고 수동: `.venv/bin/python run.py` 후 브라우저에서 "보정 확인" 탭이 뜨고 서브탭 전환·모델 select이 보이는지 육안 확인.

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/templates/index.html econ_cam/static/app.js econ_cam/static/style.css tests/test_frontend.py
git commit -m "feat(rectify): Mode 4 UI — intrinsic compute + live rectify view (single/multi)"
```

---

### Task 8: 문서 갱신 (USAGE.md / CLAUDE.md / spec 노트)

**Files:**
- Modify: `docs/USAGE.md`
- Modify: `CLAUDE.md` (프로젝트 개요의 "모드 3개" → Mode 4 추가, 파일 목록에 `calib_intrinsics.py`)
- Modify: `docs/superpowers/specs/2026-07-06-econ-multicam-test-design.md` (갱신 노트 한 줄: Mode 4 추가, cv2 계산이 이제 범위 내)

- [ ] **Step 1: USAGE.md 에 Mode 4 절 추가** — 워크플로 기술:
  1. Mode 3에서 카메라별 intrinsic 세션 촬영(단일, 자세 다양화) → 저장.
  2. Mode 4 "단일" 서브탭: 세션 선택 + 모델(Pinhole/Fisheye) 선택 → "Intrinsic 계산"(이미 계산돼 있으면 캐시 재사용, "재계산" 체크 시 강제) → RMS 확인 → 좌(원본)/우(보정) 라이브 비교.
  3. Mode 4 "다중" 서브탭: 각 카메라의 활성 intrinsic이 있어야 함 → 카메라 선택 → "라이브 시작" → 보정 그리드, 원본/보정 토글로 비교.
  - Extrinsic(카메라 간 배치)은 이 모드의 범위 밖(별도)임을 명시.
  - 저장 위치: 세션 캐시 `captures/calib/intrinsic/<세션>/intrinsics_<model>.json`, 활성본 `captures/calib/intrinsics/video<dev>.json`.
  - 성능 주의: 보정 프리뷰는 CPU `remap`이라 프리뷰 해상도(640×360)에서 동작.

- [ ] **Step 2: CLAUDE.md 갱신** — "모드 3개" → "모드 4개(… / 보정 확인)"; 기술 결정에 "Mode 4 실시간 보정도 cv2 사용(계산·remap)"; 파일 목록에 `calib_intrinsics.py`(cv2) 추가.

- [ ] **Step 3: spec 갱신 노트 추가** — 상단 갱신 노트에 "2026-07-09: Mode 4(보정 확인) 추가 — 실제 intrinsic 계산 + 실시간 undistort 시각화. Extrinsic 계산은 여전히 범위 밖." 한 줄.

- [ ] **Step 4: 전체 테스트 회귀 확인** — Run: `.venv/bin/python -m pytest -q`  Expected: 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add docs/USAGE.md CLAUDE.md docs/superpowers/specs/2026-07-06-econ-multicam-test-design.md
git commit -m "docs: document Mode 4 (rectification) usage + scope update"
```

---

## Verification (엔드-투-엔드)

**자동 (하드웨어 불필요):**
- `.venv/bin/python -m pytest -q` — 신규 `test_calib_board.py`(격자), `test_calib_intrinsics.py`(합성 checkerboard로 pinhole·fisheye 계산 RMS<1, 저장/로드, undistort 맵·remap), `test_app.py`(compute 캐시-재사용/활성본 기록, 스트림 라우트 200/404), `test_frontend.py`(새 탭) 전부 PASS + 기존 테스트 회귀 없음.

**수동 (실제 4대 하드웨어) — `.venv/bin/python run.py` 후 브라우저:**
1. **단일 계산:** Mode 3에서 한 카메라의 intrinsic 세션(자세 다양) 촬영·저장 → Mode 4 "단일"에서 세션 선택 → Pinhole "Intrinsic 계산" → **RMS가 표시**되고(대략 <1px면 양호) 좌(광각 원본)/우(직선이 펴진 보정)가 라이브로 나란히 보임. 격자·직선 물체를 대보고 우측에서 직선성이 개선되는지 확인.
2. **모델 비교:** 같은 세션에서 Fisheye로 바꿔 재계산(또는 "재계산") → 광각이 강하면 fisheye 쪽 보정/RMS가 더 나은지 비교.
3. **캐시:** 같은 세션·모델로 다시 "Intrinsic 계산" → 상태에 "(캐시)" 표시, 즉시 반환.
4. **다중 라이브:** 카메라 4대 각각 intrinsic을 계산·활성화한 뒤 Mode 4 "다중" → "라이브 시작" → 4분할 보정 그리드가 동시에 나오고, **원본/보정 토글**로 각 셀이 원본↔보정으로 즉시 전환됨.
5. **미보정 카메라 처리:** 활성 intrinsic이 없는 카메라는 보정 스트림이 404 → 해당 셀이 비거나 상태 문구로 안내되는지 확인.

## Self-Review 메모

- **스펙 커버리지:** intrinsic 실계산(Task 2), 단일 보정 시각화(Task 6·7), 다중 실시간 보정(Task 6·7), 폴더 지정→계산(Task 5), "있으면 재사용/없으면 계산"(Task 5 캐시), pinhole/fisheye UI 선택(Task 2·7), checkerboard+charuco(Task 2), extrinsic 제외(문서 명시, Task 8) — 모두 태스크에 매핑됨.
- **타입 일관성:** `Intrinsics`(model,K,dist,image_size,rms,per_view_errors,n_images,board), `compute_intrinsics`/`build_undistort_maps(out_size)`/`rectify_jpeg(jpeg,maps)`, 라우트 `/api/rectify/compute|intrinsics/<dev>|stream/<dev>|sync/stream/<dev>`, `_active_intr_path`/`INTR_DIR` — 태스크 간 명칭 일치 확인.
- **주의점(구현자):** charuco 계산에는 ID가 필요(기존 `detect_board`는 ID를 버림) → `calib_intrinsics.correspondences`가 charuco를 재검출. 라이브 보정은 CPU라 프리뷰 해상도 전용(K 스케일). `get_or_start_stream`은 `create_app` 클로저 — 스트림 테스트는 상태코드 위주.
