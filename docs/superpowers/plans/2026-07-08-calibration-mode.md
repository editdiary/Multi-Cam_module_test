# Calibration Mode (Mode 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **When executing, also copy this file to `docs/superpowers/plans/2026-07-08-calibration-mode.md`** (plan mode only permitted writing here).

**Goal:** Build Mode 3 "캘리브레이션" as an image *collection + validation* tool with two sub-modes — Intrinsic (single-camera, checkerboard/ChArUco) and Extrinsic (4-camera synchronized, pairwise-overlap) — that gate each shot through a quality-validation pipeline, only allow saving validated images, monitor collected counts, and guide the user toward diverse poses/distances.

**Architecture:** Reuse the existing GStreamer capture plumbing (`Camera` for intrinsic previews/capture, `SyncSession` for extrinsic synced capture). Add cv2-based board detection + quality metrics and *pure* decision logic (verdict, coverage, diversity) in new focused modules. Server-side accumulator state lives in `app.py`'s `state` dict (matching the existing pattern). Frontend replaces the `#calib` skeleton with a board-config form + sub-tabs, following the existing Mode 1/Mode 2 UI conventions.

**Tech Stack:** Flask, GStreamer (`gi`, existing), **new: `opencv-contrib-python` + numpy (venv only)**, vanilla JS frontend, pytest.

**Scope (confirmed with user):** Collection + validation ONLY. NO intrinsic/extrinsic matrix computation in v1 — output is validated image folders + JSON metadata for an offline calibration step. Both checkerboard (default) and ChArUco boards selectable. 4-camera arrangement is ring/array (adjacent-pair overlap → pairwise-chaining collection). Pose-diversity guidance included in v1.

## Context

Mode 3 is currently a one-line skeleton (`templates/index.html:58` placeholder, no JS branch, no routes). The user wants a real calibration-image collection workflow. The core need: capturing calibration images by hand is error-prone (blurry, board cut off, bad exposure, too-similar poses) and failures only surface later when calibration diverges. This mode moves that feedback to capture time — every shot is validated before it can be saved, the UI tracks how many good images exist, and it steers the user to under-covered poses/distances. Extrinsic adds the multi-camera dimension: for a ring/array of 4 cameras where only adjacent pairs overlap, the tool collects synchronized shots where the board is clearly seen by an adjacent pair, and tracks per-pair coverage so all links in the chain get enough data.

**Extrinsic methodology note (informs the design + in-UI guide):** For camera-to-camera extrinsics you do NOT need the board's absolute room position. You need the board visible **simultaneously in overlapping camera pairs**; the square size provides metric scale, and each shot's board pose is the shared reference between the two cameras that see it. With a ring/array where only neighbors overlap, extrinsics are obtained by stereo-calibrating each adjacent pair (0-1, 1-2, 2-3, optionally 3-0) and chaining the relative transforms. The tool therefore collects & validates synchronized image sets and records which pairs saw the board — the actual stereo/chaining computation is an offline follow-up (out of v1 scope).

## Global Constraints

- **No host apt changes.** New Python deps go into the venv via `pip` only (`.venv`, `--system-site-packages`). — copied from CLAUDE.md.
- **cv2 = new dependency, venv only:** `opencv-contrib-python==4.8.1.78` (aarch64 cp310 wheel confirmed on PyPI; ChArUco `CharucoDetector` requires ≥4.7; numpy floor 1.21.2 ≤ system numpy 1.21.5, so system numpy is reused, not reinstalled).
- **Reuse, don't duplicate, capture plumbing:** intrinsic uses `capture.Camera` + `/api/stream/<dev>/mjpeg`; extrinsic uses `capture.SyncSession` + `/api/sync/start` + `/api/sync/stream/<dev>`.
- **Pure logic separated & unit-tested without hardware:** board config, verdict, coverage, diversity are pure (plain numbers/dicts, no cv2). cv2 detection is integration-tested with a synthetic board image (no camera needed).
- **Validation hard-blocks save; redundancy only warns.** A shot failing detection/blur/exposure/position/size cannot be saved. A shot that passes but duplicates an existing pose is still savable but flagged.
- **File-per-concern, small files** (project rule). Korean UI text, matching existing style.

## File Structure

**New backend modules** (all under `econ_cam/`):
- `calib_board.py` — `BoardConfig` dataclass, `parse_board_config()`, `adjacent_pairs()`. Pure. Testable without cv2.
- `calib_quality.py` — `verdict_from_metrics()`, `coverage_state()`, `diversity_check()` + threshold constants. Pure. Testable without cv2.
- `calib_detect.py` — cv2 board detection, quality-metric extraction, pose descriptor, corner overlay. Needs cv2+numpy.

**Modified backend:**
- `econ_cam/app.py` — add `state["calib"]` accumulator + `_calib_evaluate()` helper + routes `/api/calib/{start,capture,accept,status,reset}`.
- `requirements.txt` — add opencv-contrib-python.

**Modified frontend:**
- `econ_cam/templates/index.html` — replace `#calib` skeleton (lines 58-60) with board form + sub-tabs + intrinsic/extrinsic panels.
- `econ_cam/static/app.js` — add `calib` branch to `setMode`, sub-tab switching, board-form handling, session/capture/accept flow, status/coverage rendering.
- `econ_cam/static/style.css` — sub-tab, coverage-grid, verdict-banner classes.

**New tests** (`tests/`):
- `test_calib_board.py`, `test_calib_quality.py` (pure), `test_calib_detect.py` (cv2 integration with synthetic board).

**Docs:**
- `docs/USAGE.md` — add calibration-mode section incl. the extrinsic pairwise-chaining guide.

**Saved artifacts on disk:**
```
captures/calib/intrinsic/<YYYYMMDD_HHMMSS>/
    board_config.json
    video<dev>/frame_000.jpg, frame_001.jpg, ...
    report.json              # [{file, metrics, descriptor}, ...]
captures/calib/extrinsic/<YYYYMMDD_HHMMSS>/
    board_config.json
    shot_000/video0.jpg,video1.jpg,...  + detections.json (per-cam detected/corner_count/sync_stats)
    report.json              # per-shot pair coverage
```

---

## Task 1: Add OpenCV dependency to venv

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependency**

Edit `requirements.txt` to:
```
flask
opencv-contrib-python==4.8.1.78
```

- [ ] **Step 2: Install into venv**

Run: `/home/cv_pretest/Desktop/Multi-Cam_module_test/.venv/bin/pip install -r requirements.txt`
Expected: installs opencv-contrib-python (aarch64 wheel); numpy 1.21.5 already satisfied from system-site-packages (not reinstalled).

- [ ] **Step 3: Smoke-test imports (incl. ChArUco API)**

Run:
```
/home/cv_pretest/Desktop/Multi-Cam_module_test/.venv/bin/python -c "import cv2, numpy; import cv2.aruco as a; print(cv2.__version__, numpy.__version__, hasattr(a,'CharucoDetector'), hasattr(cv2,'findChessboardCornersSB'))"
```
Expected: `4.8.1.78 1.21.5 True True`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "build: add opencv-contrib-python (venv) for calibration validation"
```

---

## Task 2: `calib_board.py` — board config + camera-pair topology (pure)

**Files:**
- Create: `econ_cam/calib_board.py`
- Test: `tests/test_calib_board.py`

**Interfaces — Produces (later tasks rely on these):**
- `BoardConfig` dataclass: fields `board_type:str`, `cols:int`, `rows:int`, `square_mm:float`, `marker_mm:float=0.0`, `dictionary:str="DICT_5X5_100"`; property `expected_corners:int`; method `to_dict()->dict`.
- `parse_board_config(d:dict) -> BoardConfig` (raises `ValueError` on invalid).
- `adjacent_pairs(devs:list[int], ring:bool=False) -> list[tuple[int,int]]`.
- `DICTS: list[str]` (ArUco dictionaries exposed to UI).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_calib_board.py
import pytest
from econ_cam.calib_board import parse_board_config, adjacent_pairs, BoardConfig

def test_checkerboard_expected_corners():
    cfg = parse_board_config({"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25})
    assert cfg.expected_corners == 54
    assert cfg.marker_mm == 0.0

def test_charuco_requires_valid_marker_and_dict():
    cfg = parse_board_config({"board_type": "charuco", "cols": 5, "rows": 7,
                              "square_mm": 30, "marker_mm": 22, "dictionary": "DICT_5X5_100"})
    assert cfg.expected_corners == (5 - 1) * (7 - 1)  # inner chessboard corners
    with pytest.raises(ValueError):
        parse_board_config({"board_type": "charuco", "cols": 5, "rows": 7,
                            "square_mm": 30, "marker_mm": 30})   # marker not < square

def test_invalid_inputs():
    with pytest.raises(ValueError):
        parse_board_config({"board_type": "nope", "cols": 9, "rows": 6, "square_mm": 25})
    with pytest.raises(ValueError):
        parse_board_config({"board_type": "checkerboard", "cols": 1, "rows": 6, "square_mm": 25})
    with pytest.raises(ValueError):
        parse_board_config({"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 0})

def test_adjacent_pairs_array_and_ring():
    assert adjacent_pairs([0, 1, 2, 3]) == [(0, 1), (1, 2), (2, 3)]
    assert adjacent_pairs([3, 0, 2, 1], ring=True) == [(0, 1), (1, 2), (2, 3), (0, 3)]
    assert adjacent_pairs([0, 1], ring=True) == [(0, 1)]   # no wrap for a single pair

def test_to_dict_roundtrip():
    cfg = parse_board_config({"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25})
    d = cfg.to_dict()
    assert parse_board_config(d).expected_corners == 54
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_calib_board.py -v`
Expected: FAIL (ModuleNotFoundError: econ_cam.calib_board).

- [ ] **Step 3: Implement `calib_board.py`**

```python
"""Checkerboard/ChArUco board configuration + camera-pair topology. Pure, no cv2."""
from dataclasses import dataclass, asdict

DICTS = ["DICT_4X4_50", "DICT_5X5_100", "DICT_6X6_250", "DICT_7X7_1000"]


@dataclass
class BoardConfig:
    board_type: str          # "checkerboard" | "charuco"
    cols: int                # checkerboard: inner corners per row; charuco: squares in X
    rows: int                # checkerboard: inner corners per col; charuco: squares in Y
    square_mm: float         # physical square size (mm)
    marker_mm: float = 0.0   # charuco only: ArUco marker size (mm)
    dictionary: str = "DICT_5X5_100"   # charuco only

    @property
    def expected_corners(self) -> int:
        if self.board_type == "checkerboard":
            return self.cols * self.rows
        return (self.cols - 1) * (self.rows - 1)   # charuco inner chessboard corners

    def to_dict(self) -> dict:
        return asdict(self)


def parse_board_config(d: dict) -> BoardConfig:
    bt = d.get("board_type", "checkerboard")
    if bt not in ("checkerboard", "charuco"):
        raise ValueError(f"unknown board_type: {bt}")
    cols, rows = int(d["cols"]), int(d["rows"])
    if cols < 2 or rows < 2:
        raise ValueError("cols/rows must be >= 2")
    square_mm = float(d["square_mm"])
    if square_mm <= 0:
        raise ValueError("square_mm must be > 0")
    cfg = BoardConfig(bt, cols, rows, square_mm)
    if bt == "charuco":
        cfg.marker_mm = float(d.get("marker_mm", 0))
        if not (0 < cfg.marker_mm < square_mm):
            raise ValueError("marker_mm must be > 0 and < square_mm")
        cfg.dictionary = d.get("dictionary", "DICT_5X5_100")
        if cfg.dictionary not in DICTS:
            raise ValueError(f"unknown dictionary: {cfg.dictionary}")
    return cfg


def adjacent_pairs(devs: list, ring: bool = False) -> list:
    """Overlapping camera pairs. Linear array: (0,1),(1,2),... Ring adds (first,last)."""
    s = sorted(devs)
    pairs = [(s[i], s[i + 1]) for i in range(len(s) - 1)]
    if ring and len(s) > 2:
        pairs.append((s[0], s[-1]))
    return pairs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_calib_board.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add econ_cam/calib_board.py tests/test_calib_board.py
git commit -m "feat(calib): board config + camera-pair topology (pure)"
```

---

## Task 3: `calib_quality.py` — verdict + coverage + diversity (pure)

**Files:**
- Create: `econ_cam/calib_quality.py`
- Test: `tests/test_calib_quality.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `THRESH: dict` (tunable thresholds).
  - `verdict_from_metrics(m:dict, t:dict=THRESH) -> {"ok":bool, "reasons":[str], "checks":{str:bool}}`. `m` keys: `board_type,detected,corner_ratio,sharpness,roi_mean,clip_frac,dark_frac,min_edge_frac,area_frac`.
  - `coverage_state(descs:list[dict]) -> {"cells":{str:int}, "filled":int, "total":int, "suggestions":[str]}`. Each desc: `{center_x,center_y,area_frac}` in [0,1].
  - `diversity_check(new_desc:dict, descs:list[dict]) -> {"novel":bool, "suggestion":str}`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_calib_quality.py
from econ_cam.calib_quality import verdict_from_metrics, coverage_state, diversity_check

GOOD = {"board_type": "checkerboard", "detected": True, "corner_ratio": 1.0,
        "sharpness": 300.0, "roi_mean": 130.0, "clip_frac": 0.0, "dark_frac": 0.0,
        "min_edge_frac": 0.10, "area_frac": 0.20}

def test_verdict_pass():
    v = verdict_from_metrics(GOOD)
    assert v["ok"] is True and v["reasons"] == []

def test_verdict_not_detected():
    v = verdict_from_metrics({**GOOD, "detected": False, "corner_ratio": 0.0})
    assert v["ok"] is False and any("찾지" in r for r in v["reasons"])

def test_verdict_blur_and_edge_fail():
    v = verdict_from_metrics({**GOOD, "sharpness": 20.0, "min_edge_frac": 0.001})
    assert v["ok"] is False
    assert v["checks"]["sharpness"] is False and v["checks"]["position"] is False

def test_verdict_exposure_fail():
    assert verdict_from_metrics({**GOOD, "roi_mean": 245.0})["checks"]["exposure"] is False
    assert verdict_from_metrics({**GOOD, "clip_frac": 0.2})["checks"]["exposure"] is False

def test_charuco_partial_corners_ok_but_checkerboard_not():
    partial = {**GOOD, "corner_ratio": 0.6}
    assert verdict_from_metrics({**partial, "board_type": "checkerboard"})["checks"]["corners"] is False
    assert verdict_from_metrics({**partial, "board_type": "charuco"})["checks"]["corners"] is True

def test_coverage_and_diversity():
    d_center = {"center_x": 0.5, "center_y": 0.5, "area_frac": 0.10}
    cov = coverage_state([d_center])
    assert cov["filled"] == 1 and cov["total"] == 27 and len(cov["suggestions"]) > 0
    # same cell -> not novel; far corner + different distance -> novel
    assert diversity_check(d_center, [d_center])["novel"] is False
    assert diversity_check({"center_x": 0.05, "center_y": 0.05, "area_frac": 0.02},
                           [d_center])["novel"] is True
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/test_calib_quality.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `calib_quality.py`**

```python
"""Pure decision logic for calibration image validation & pose-diversity coverage.
Plain numbers/dicts only — no cv2/numpy (testable without hardware)."""

THRESH = {
    "min_sharpness": 100.0,   # variance-of-Laplacian floor (blur gate)
    "bright_lo": 40.0,        # board-ROI mean brightness floor (0-255)
    "bright_hi": 220.0,       # ceiling
    "max_clip_frac": 0.05,    # fraction of near-saturated (>=250) ROI pixels allowed
    "max_dark_frac": 0.05,    # fraction of near-black (<=5) ROI pixels allowed
    "edge_margin_frac": 0.02, # nearest corner must be >=2% of min(w,h) from every edge
    "min_area_frac": 0.03,    # board convex hull must fill >=3% of frame
    "charuco_min_ratio": 0.5, # charuco: >=50% of inner corners detected
}

COVER_GRID = 3                 # 3x3 spatial regions
DIST_BINS = (0.06, 0.15)       # area_frac splits -> far / mid / near
_REGION_NAME = {(0, 0): "좌상단", (1, 0): "상단", (2, 0): "우상단",
                (0, 1): "좌측", (1, 1): "중앙", (2, 1): "우측",
                (0, 2): "좌하단", (1, 2): "하단", (2, 2): "우하단"}
_DIST_NAME = {0: "원거리", 1: "중거리", 2: "근거리"}


def verdict_from_metrics(m: dict, t: dict = THRESH) -> dict:
    checks, reasons = {}, []

    def check(name, cond, msg):
        checks[name] = bool(cond)
        if not cond:
            reasons.append(msg)

    check("detected", m["detected"], "체커보드를 찾지 못했습니다")
    if m["detected"]:
        if m["board_type"] == "checkerboard":
            check("corners", m["corner_ratio"] >= 0.999, "교차점이 일부만 검출되었습니다")
        else:
            check("corners", m["corner_ratio"] >= t["charuco_min_ratio"],
                  "교차점이 너무 적게 검출되었습니다")
        check("sharpness", m["sharpness"] >= t["min_sharpness"], "이미지가 흐립니다 (초점/흔들림)")
        check("exposure",
              t["bright_lo"] <= m["roi_mean"] <= t["bright_hi"]
              and m["clip_frac"] <= t["max_clip_frac"] and m["dark_frac"] <= t["max_dark_frac"],
              "명암이 부적절합니다 (과노출/과소노출)")
        check("position", m["min_edge_frac"] >= t["edge_margin_frac"],
              "보드가 화면 가장자리에 잘렸습니다")
        check("size", m["area_frac"] >= t["min_area_frac"], "보드가 너무 작습니다 (더 가까이)")
    ok = all(checks.values())
    return {"ok": ok, "reasons": reasons, "checks": checks}


def _cell(desc: dict):
    cx = min(COVER_GRID - 1, int(desc["center_x"] * COVER_GRID))
    cy = min(COVER_GRID - 1, int(desc["center_y"] * COVER_GRID))
    a = desc["area_frac"]
    d = 0 if a < DIST_BINS[0] else (1 if a < DIST_BINS[1] else 2)
    return (cx, cy, d)


def coverage_state(descs: list) -> dict:
    cells = {}
    for de in descs:
        k = "%d,%d,%d" % _cell(de)
        cells[k] = cells.get(k, 0) + 1
    total = COVER_GRID * COVER_GRID * len(DIST_BINS) + COVER_GRID * COVER_GRID  # 3*3*3 = 27
    suggestions = []
    for d in range(3):
        for cy in range(COVER_GRID):
            for cx in range(COVER_GRID):
                if "%d,%d,%d" % (cx, cy, d) not in cells:
                    suggestions.append(f"{_REGION_NAME[(cx, cy)]}·{_DIST_NAME[d]}")
    return {"cells": cells, "filled": len(cells), "total": total, "suggestions": suggestions[:5]}


def diversity_check(new_desc: dict, descs: list) -> dict:
    k = _cell(new_desc)
    same = sum(1 for de in descs if _cell(de) == k)
    if same == 0:
        return {"novel": True, "suggestion": ""}
    cx, cy, d = k
    return {"novel": False,
            "suggestion": f"{_REGION_NAME[(cx, cy)]}·{_DIST_NAME[d]} 구도는 이미 있습니다. "
                          f"다른 위치/거리에서 촬영을 권장합니다."}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_calib_quality.py -v`
Expected: PASS (6 tests). (Note `total == 27` = 3×3×3 cells.)

- [ ] **Step 5: Commit**

```bash
git add econ_cam/calib_quality.py tests/test_calib_quality.py
git commit -m "feat(calib): verdict + pose coverage/diversity logic (pure)"
```

---

## Task 4: `calib_detect.py` — cv2 detection, metrics, descriptor, overlay

**Files:**
- Create: `econ_cam/calib_detect.py`
- Test: `tests/test_calib_detect.py`

**Interfaces:**
- Consumes: `calib_board.BoardConfig`, `calib_quality` thresholds (indirectly).
- Produces:
  - `detect_board(jpeg:bytes, cfg:BoardConfig) -> (gray_ndarray, corners_Nx2_float32_or_None, count:int)`
  - `quality_metrics(gray, corners, cfg) -> dict` (keys match `verdict_from_metrics` input).
  - `pose_descriptor(gray, corners) -> {"center_x","center_y","area_frac"}`
  - `overlay_corners(jpeg:bytes, cfg, corners) -> bytes` (JPEG with corners drawn, for UI feedback).
  - `render_board_jpeg(cfg, px:int=900) -> bytes` (renders a printable board image; used by an optional "board preview" and by tests to generate a synthetic detectable board).

- [ ] **Step 1: Write failing integration tests (synthetic board, no camera)**

```python
# tests/test_calib_detect.py
import cv2, numpy as np
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
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/test_calib_detect.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `calib_detect.py`**

```python
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
    board = cv2.aruco.CharucoBoard((cfg.cols, cfg.rows), cfg.square_mm, cfg.marker_mm, dic)
    return board


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
        m.update(sharpness=0.0, roi_mean=0.0, clip_frac=1.0,
                 dark_frac=1.0, min_edge_frac=0.0, area_frac=0.0)
        return m
    xs, ys = corners[:, 0], corners[:, 1]
    x0, y0 = max(int(xs.min()), 0), max(int(ys.min()), 0)
    x1, y1 = min(int(xs.max()) + 1, w), min(int(ys.max()) + 1, h)
    roi = gray[y0:y1, x0:x1]
    m["sharpness"] = float(cv2.Laplacian(roi, cv2.CV_64F).var())
    m["roi_mean"] = float(roi.mean())
    m["clip_frac"] = float((roi >= 250).mean())
    m["dark_frac"] = float((roi <= 5).mean())
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_calib_detect.py -v`
Expected: PASS (5 tests). If `render_board_jpeg` charuco detection is marginal, the test tolerates ≥50% corners.

- [ ] **Step 5: Run full suite (ensure no regressions)**

Run: `.venv/bin/python -m pytest -v`
Expected: all existing + new tests PASS.

- [ ] **Step 6: Commit**

```bash
git add econ_cam/calib_detect.py tests/test_calib_detect.py
git commit -m "feat(calib): cv2 board detection, quality metrics, descriptor, overlay"
```

---

## Task 5: Backend — calib session state + intrinsic routes

**Files:**
- Modify: `econ_cam/app.py`

**Interfaces:**
- Consumes: `calib_board.parse_board_config`, `calib_detect.{detect_board,quality_metrics,pose_descriptor,overlay_corners}`, `calib_quality.{verdict_from_metrics,coverage_state,diversity_check}`, existing `get_or_start_stream(dev)`, `jpeg_to_data_uri`, `CAPTURE_DIR`.
- Produces routes consumed by frontend Task 8:
  - `POST /api/calib/start` body `{sub_mode, board, devices, ring?}` → `{ok, sub_mode, board, session_dir, counts, pairs?}`
  - `POST /api/calib/capture` → `{ok, verdict, metrics, overlay:{str(dev):dataURI}, diversity, sync_stats?}`
  - `POST /api/calib/accept` → `{ok, counts, coverage, pairs?}` or 400
  - `GET /api/calib/status` → `{active, sub_mode?, board?, counts?, coverage?, pairs?}`
  - `POST /api/calib/reset` → `{ok}`

**Design details:**
- Add to `state` dict: `"calib": None`. When a session is active it holds:
  ```python
  {"sub_mode": "intrinsic"|"extrinsic", "cfg": BoardConfig, "devices": [int], "ring": bool,
   "session_dir": str, "descs": {dev:[desc]}, "reports": {dev:[{file,metrics}]},
   "pair_counts": {(a,b): int},         # extrinsic only
   "pending": None }                    # last captured, not-yet-saved candidate
  ```
- Add helper `_calib_evaluate(dev, jpeg, cfg) -> dict`:
  ```python
  gray, corners, n = calib_detect.detect_board(jpeg, cfg)
  metrics = calib_detect.quality_metrics(gray, corners, cfg)
  verdict = calib_quality.verdict_from_metrics(metrics)
  desc = calib_detect.pose_descriptor(gray, corners) if corners is not None else None
  overlay = calib_detect.overlay_corners(jpeg, cfg, corners)
  return {"jpeg": jpeg, "overlay": overlay, "metrics": metrics,
          "verdict": verdict, "desc": desc}
  ```
- `/api/calib/start`: under `state["lock"]`, `stop_streams()`+`stop_sync()`, `parse_board_config`, create `captures/calib/<sub_mode>/<ts>/`, dump `board_config.json`, init accumulator (empty `descs`/`reports`; for extrinsic init `pair_counts` from `adjacent_pairs(devices, ring)`), set `state["calib"]`.
- `/api/calib/capture` (intrinsic branch this task): `dev = state["calib"]["devices"][0]`; `cam = get_or_start_stream(dev)`; `jpeg, _pts = cam.capture()`; `ev = _calib_evaluate(dev, jpeg, cfg)`; `diversity = diversity_check(ev["desc"], descs[dev]) if ev["desc"] else {"novel":True,"suggestion":""}`; store `state["calib"]["pending"] = {dev: ev}`; return verdict/metrics/overlay(data-uri)/diversity.
- `/api/calib/accept` (intrinsic branch): require `pending` and all its `ev["verdict"]["ok"]`; else 400 `{ok:false,error:"검증 미통과"}`. For each dev: write JPEG to `session_dir/video<dev>/frame_<NNN>.jpg` (NNN = current count, zero-padded), append `desc`→`descs[dev]`, append `{file,metrics}`→`reports[dev]`; rewrite `report.json`. Clear `pending`. Return `counts={str(dev):len}` and `coverage=coverage_state(descs[dev])`.
- `/api/calib/status`: if no session `{active:false}`; else counts + coverage (intrinsic: for the single dev).
- `/api/calib/reset`: clear `state["calib"]=None`.

- [ ] **Step 1: Add imports + `state["calib"]` + `_calib_evaluate` helper**

Add near existing imports in `app.py`:
```python
from econ_cam import calib_board, calib_detect, calib_quality
```
Add `"calib": None,` to the `state` dict. Add `_calib_evaluate` and a `_calib_dir` helper (`os.path.join(CAPTURE_DIR, "calib")`).

- [ ] **Step 2: Implement `/api/calib/start`, `/capture`, `/accept`, `/status`, `/reset` (intrinsic paths)**

Follow the design details above. Reuse `jpeg_to_data_uri` for overlay images: `overlay={str(dev): jpeg_to_data_uri(ev["overlay"])}`.

- [ ] **Step 3: Manual route smoke test (no camera needed for validation-logic path)**

Run a Python snippet against the Flask test client feeding a synthetic board JPEG through `_calib_evaluate` to confirm it returns a passing verdict (mirrors Task 4 test but via the app import). Then start the server and confirm `GET /api/calib/status` → `{"active": false}`.
Run: `.venv/bin/python -c "from econ_cam.app import create_app; c=create_app().test_client(); print(c.get('/api/calib/status').get_json())"`
Expected: `{'active': False}`

- [ ] **Step 4: Commit**

```bash
git add econ_cam/app.py
git commit -m "feat(calib): backend session state + intrinsic capture/validate/save routes"
```

---

## Task 6: Backend — extrinsic capture path (synced multi-cam + pair coverage)

**Files:**
- Modify: `econ_cam/app.py`

**Design details:**
- Extrinsic previews & sync reuse existing `/api/sync/start` + `/api/sync/stream/<dev>` (frontend calls those; `/api/calib/start` for extrinsic just records session/board/pairs, does NOT own the stream).
- `/api/calib/capture` extrinsic branch: require an active `state["sync_session"]`; `result = sess.capture()` → `{images:{dev:jpeg}, timestamps, stats}`. For each dev run `_calib_evaluate`. Build `sync_stats = _json_stats(result["stats"])`.
  - **Shot-level verdict:** a shot passes iff at least one adjacent pair has BOTH cameras' `verdict["ok"]` true. Compute `covered_pairs = [(a,b) for (a,b) in pairs if ev[a].ok and ev[b].ok]`. `verdict = {"ok": len(covered_pairs) > 0, "reasons": [...], "per_cam": {dev: ev.verdict}, "covered_pairs": covered_pairs}`. If no pair fully passes, reason lists which cameras failed and why (aggregate per-cam reasons).
  - Store `pending` = all evs + covered_pairs + sync_stats. Return `{ok, verdict, metrics:{dev:...}, overlay:{dev:dataURI}, sync_stats, covered_pairs}`.
- `/api/calib/accept` extrinsic branch: require pending with `verdict.ok`. Create `session_dir/shot_<NNN>/`; write each `video<dev>.jpg`; write `detections.json` (`{dev:{detected,corner_count,metrics}, covered_pairs, sync_stats}`); increment `pair_counts[(a,b)]` for each covered pair; append shot descriptor. Rewrite `report.json` (per-shot list + pair_counts). Return `counts={"shots":N}`, `pairs=[{pair:"a-b", count:int} ...]`.
- `/api/calib/status` extrinsic branch: `{active, sub_mode:"extrinsic", counts:{shots:N}, pairs:[...], board}`.

- [ ] **Step 1: Branch `/api/calib/capture` and `/api/calib/accept` on `sub_mode`**

Add the extrinsic branches per design. Reuse existing `_json_stats`.

- [ ] **Step 2: Extend `/api/calib/status` for extrinsic (pair coverage)**

- [ ] **Step 3: Smoke test**

Start server, `POST /api/calib/start {sub_mode:"extrinsic", board:{...}, devices:[0,1,2,3], ring:false}`, `GET /api/calib/status` → confirm `pairs` = `[{"pair":"0-1","count":0},{"pair":"1-2",...},{"pair":"2-3",...}]`.
(Capture itself requires hardware — deferred to Task 11.)

- [ ] **Step 4: Commit**

```bash
git add econ_cam/app.py
git commit -m "feat(calib): extrinsic synced capture + adjacent-pair coverage routes"
```

---

## Task 7: Frontend scaffolding — HTML sub-tabs, board form, CSS

**Files:**
- Modify: `econ_cam/templates/index.html` (replace lines 58-60, the `#calib` skeleton)
- Modify: `econ_cam/static/style.css`

**Design details** — replace the `#calib` section with a `.card` containing: (1) a shared board-config form, (2) a `.subtabs` row with two buttons (`data-sub="intrinsic"`/`data-sub="extrinsic"`), (3) two `.submode` panels. Reuse existing `.toolbar`, `.actions`, `.status-line`, `.view`, `.grid`, `.checkboxes`, `.placeholder`, `toast`.

- [ ] **Step 1: Replace `#calib` skeleton with the structure below**

```html
<section id="calib" class="mode">
  <div class="card">
    <!-- Shared board config -->
    <div class="board-form">
      <label>보드 종류
        <select id="calib-board-type">
          <option value="checkerboard" selected>체커보드</option>
          <option value="charuco">ChArUco</option>
        </select>
      </label>
      <label>교차점(가로) <input id="calib-cols" type="number" min="2" value="9"></label>
      <label>교차점(세로) <input id="calib-rows" type="number" min="2" value="6"></label>
      <label>칸 크기(mm) <input id="calib-square" type="number" min="1" step="0.1" value="25"></label>
      <label class="charuco-only" hidden>마커 크기(mm) <input id="calib-marker" type="number" step="0.1" value="18"></label>
      <label class="charuco-only" hidden>사전
        <select id="calib-dict">
          <option>DICT_4X4_50</option><option selected>DICT_5X5_100</option>
          <option>DICT_6X6_250</option><option>DICT_7X7_1000</option>
        </select>
      </label>
      <span class="hint" id="calib-board-hint"></span>
    </div>

    <nav class="subtabs">
      <button class="subtab active" data-sub="intrinsic">Intrinsic (단일)</button>
      <button class="subtab" data-sub="extrinsic">Extrinsic (다중 동기)</button>
    </nav>

    <!-- Intrinsic -->
    <div id="calib-intrinsic" class="submode active">
      <div class="toolbar">
        <div class="toolbar-left"><select id="calib-int-cam"></select></div>
        <div class="actions">
          <button id="calib-int-start">세션 시작</button>
          <button id="calib-int-capture" disabled>Capture</button>
          <button id="calib-int-save" disabled>저장</button>
        </div>
      </div>
      <div id="calib-int-status" class="status-line"></div>
      <div id="calib-int-verdict" class="verdict" hidden></div>
      <div id="calib-int-coverage" class="coverage"></div>
      <div class="view">
        <img id="calib-int-preview" alt="preview">
        <img id="calib-int-still" hidden alt="still">
      </div>
    </div>

    <!-- Extrinsic -->
    <div id="calib-extrinsic" class="submode">
      <div class="toolbar">
        <div class="toolbar-left checkboxes" id="calib-ext-cams"></div>
        <div class="actions">
          <label class="inline"><input type="checkbox" id="calib-ext-ring"> 링 배열</label>
          <button id="calib-ext-start">세션 시작</button>
          <button id="calib-ext-capture" disabled>Sync Capture</button>
          <button id="calib-ext-save" disabled>저장</button>
        </div>
      </div>
      <div id="calib-ext-status" class="status-line"></div>
      <div id="calib-ext-verdict" class="verdict" hidden></div>
      <div id="calib-ext-pairs" class="coverage"></div>
      <details class="guide"><summary>4-카메라 Extrinsic 촬영 가이드</summary>
        <div id="calib-ext-guide"></div></details>
      <div id="calib-ext-grid" class="grid"></div>
    </div>
  </div>
</section>
```

- [ ] **Step 2: Add CSS** (append to `style.css`, reusing existing color tokens)

```css
.board-form { display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin-bottom:12px; }
.board-form label { display:flex; flex-direction:column; font-size:12px; color:#aaa; gap:4px; }
.board-form input { width:90px; background:#333; color:#eee; border:1px solid #555; border-radius:6px; padding:4px; }
.board-form .hint { color:#888; font-size:12px; }
.subtabs { display:flex; gap:6px; margin-bottom:12px; }
.subtab { background:#333; color:#ccc; border:none; padding:6px 14px; border-radius:6px; font-weight:600; }
.subtab.active { background:#2d7; color:#062; }
.submode { display:none; }
.submode.active { display:block; }
.verdict { padding:10px 14px; border-radius:8px; margin:8px 0; font-weight:600; }
.verdict.pass { background:#14351f; color:#7fdca0; }
.verdict.fail { background:#3a1616; color:#ffb0b0; }
.verdict ul { margin:6px 0 0; padding-left:18px; font-weight:400; }
.coverage { color:#bbb; font-size:13px; margin:6px 0; }
.coverage .missing { color:#e5c451; }
.inline { display:flex; align-items:center; gap:6px; color:#ccc; }
.guide { margin:10px 0; color:#bbb; }
```

- [ ] **Step 3: Verify page renders (no JS wiring yet)**

Start server, load `/`, click 캘리브레이션 tab → board form + sub-tabs + both panels visible; charuco-only fields hidden. No console errors from missing elements.

- [ ] **Step 4: Commit**

```bash
git add econ_cam/templates/index.html econ_cam/static/style.css
git commit -m "feat(calib): frontend scaffolding — board form, sub-tabs, panels, styles"
```

---

## Task 8: Frontend JS — intrinsic wiring

**Files:**
- Modify: `econ_cam/static/app.js`

**Design details** (follow existing helper conventions: `api`, `jsonPost`, `toast`, `currentResolution`, `setMode`):
- Extend `setMode`: add `else if (mode === "calib") startCalib();`. Add matching stop in `stopStreams`/a new `stopCalib()` that clears calib preview + POSTs `/api/calib/reset` and `/api/stream/stop`/`/api/sync/stop`.
- Sub-tab switching: wire `.subtab` clicks to toggle `.active` on `.subtab` + `.submode`; store `calibSub` ("intrinsic"|"extrinsic").
- `readBoardConfig()` → builds body from the form inputs; board-type change toggles `.charuco-only` visibility and updates `#calib-board-hint` (e.g. "예상 교차점 54개").
- `loadCameras()` additionally fills `#calib-int-cam` (like `#single-cam`) and `#calib-ext-cams` (like `#multi-cams`).
- Intrinsic flow:
  - `startCalib()` (when sub=intrinsic): show preview `#calib-int-preview` `src=/api/stream/{dev}/mjpeg?t=...`, hide still, reset buttons.
  - `#calib-int-start` → `jsonPost("/api/calib/start", {sub_mode:"intrinsic", board:readBoardConfig(), devices:[dev]})`; on ok enable Capture, render status/coverage, toast.
  - `#calib-int-capture` → `jsonPost("/api/calib/capture", {})`; show `#calib-int-still` = overlay data-uri (hide preview); render verdict banner (pass/fail + reasons + diversity.suggestion); enable `#calib-int-save` iff `verdict.ok`.
  - `#calib-int-save` → `jsonPost("/api/calib/accept", {})`; on ok update counts/coverage, disable save, resume preview, toast `저장됨 (N장)`.
  - `renderCalibStatus(counts, coverage)`: status line `수집: N장 · 커버리지 filled/total`; list up to a few `coverage.suggestions` as `.missing` hints.
- Board-type select + camera select + resolution change re-run the appropriate start.

- [ ] **Step 1: Implement intrinsic JS per design (functions: `startCalib`, `stopCalib`, `readBoardConfig`, `calibIntStart`, `calibIntCapture`, `calibIntSave`, `renderCalibStatus`, `renderVerdict`)**

Representative verdict renderer:
```javascript
function renderVerdict(el, verdict, diversity) {
  el.hidden = false;
  el.className = "verdict " + (verdict.ok ? "pass" : "fail");
  let html = verdict.ok ? "✅ 검증 통과 — 저장 가능" : "❌ 검증 실패 — 다시 촬영하세요";
  if (verdict.reasons && verdict.reasons.length)
    html += "<ul>" + verdict.reasons.map(r => `<li>${r}</li>`).join("") + "</ul>";
  if (diversity && diversity.suggestion)
    html += `<div class="coverage missing">${diversity.suggestion}</div>`;
  el.innerHTML = html;
}
```

- [ ] **Step 2: Wire event listeners** (mirror the existing block at app.js:223-264) for `#calib-int-*`, `.subtab`, `#calib-board-type`, `#calib-int-cam`.

- [ ] **Step 3: Manual verify (hardware)** — deferred to Task 11; here just confirm no JS errors on tab/sub-tab switch and that `세션 시작` posts a valid board config (check Network tab / server log).

- [ ] **Step 4: Commit**

```bash
git add econ_cam/static/app.js
git commit -m "feat(calib): frontend intrinsic wiring — session/capture/validate/save"
```

---

## Task 9: Frontend JS — extrinsic wiring

**Files:**
- Modify: `econ_cam/static/app.js`

**Design details:**
- `startCalib()` (sub=extrinsic): read selected devs from `#calib-ext-cams`; `jsonPost("/api/sync/start", {devices, sync_mode:1})`; build `#calib-ext-grid` figures with `<img id="calib-ext-img-{dev}" src="/api/sync/stream/{dev}?t=...">` + figcaption (reuse Mode 2 grid-building pattern); poll `/api/sync/status` every 700ms to show live sync spread in `#calib-ext-status` (reuse `renderSyncStatus` styling logic).
- `#calib-ext-start` → `jsonPost("/api/calib/start", {sub_mode:"extrinsic", board:readBoardConfig(), devices, ring:#calib-ext-ring.checked})`; enable Capture; render pair coverage.
- `#calib-ext-capture` → `jsonPost("/api/calib/capture", {})`; freeze grid to overlay images (`data.overlay[dev]`); render shot verdict (`covered_pairs` → "동시 검출된 쌍: 0-1, 1-2"; failed cams + reasons) and `sync_stats` (spread/std); enable save iff `verdict.ok`.
- `#calib-ext-save` → `jsonPost("/api/calib/accept", {})`; update pair-coverage display (`data.pairs` → per-pair count, highlight pairs with `count < target` e.g. 6 as `.missing`), disable save, resume live grid, toast `shot 저장됨`.
- `renderPairCoverage(pairs)`: e.g. `쌍 커버리지: 0-1(4) 1-2(2) 2-3(0)` with under-target ones flagged.
- Populate `#calib-ext-guide` (static Korean text) from Task 10.

- [ ] **Step 1: Implement extrinsic JS** (functions: `calibExtStart`, `calibExtCapture`, `calibExtSave`, `renderPairCoverage`, extend `startCalib`/`stopCalib`/poll).

- [ ] **Step 2: Wire listeners** for `#calib-ext-*`, `#calib-ext-cams` change (restart sync preview), `#calib-ext-ring`.

- [ ] **Step 3: Verify** no JS errors switching to extrinsic sub-tab; `/api/sync/start` fires on camera selection.

- [ ] **Step 4: Commit**

```bash
git add econ_cam/static/app.js
git commit -m "feat(calib): frontend extrinsic wiring — synced capture, pair coverage"
```

---

## Task 10: In-UI extrinsic guide + docs

**Files:**
- Modify: `econ_cam/static/app.js` (populate `#calib-ext-guide`) or `templates/index.html` (static text)
- Modify: `docs/USAGE.md`

**Design details** — write the pairwise-chaining guidance (Korean) covering: only-adjacent-pairs-overlap arrangement; each shot needs the board clearly seen by at least one adjacent pair (tool enforces this); collect ~6+ good shots per pair across varied board angles/distances within the shared region; square size gives scale; absolute board position not required (correcting the user's assumption), but you may fix a world frame later if a global rig origin is wanted; the ring checkbox adds the (first,last) pair; the saved `detections.json`/`report.json` feed an offline stereo-calibrate + chain step (out of v1 scope). Keep the in-UI version short; put the fuller explanation in `docs/USAGE.md`.

- [ ] **Step 1: Add in-UI guide text** to `#calib-ext-guide`.
- [ ] **Step 2: Add "캘리브레이션 모드" section to `docs/USAGE.md`** (intrinsic workflow, extrinsic workflow + pairwise-chaining method, board setup, output folder layout).
- [ ] **Step 3: Commit**

```bash
git add econ_cam/static/app.js docs/USAGE.md econ_cam/templates/index.html
git commit -m "docs(calib): extrinsic pairwise-chaining guide (in-UI + USAGE)"
```

---

## Task 11: Manual hardware verification (4 cameras)

**Files:** none (verification only). Requires the 4 physical AR0234 cameras + a printed checkerboard (and optionally a ChArUco board).

- [ ] **Intrinsic:** select one camera → live preview; enter board config (e.g. 9×6, 25mm) → 세션 시작. Capture a clean board shot → verdict PASS, overlay shows all corners, 저장 enabled → 저장 → count increments, file in `captures/calib/intrinsic/<ts>/video<dev>/`. Capture a deliberately blurry / edge-cut / dark shot → verdict FAIL with correct reason, 저장 disabled. Verify coverage suggestions change as you cover different regions/distances; a near-duplicate pose triggers the redundancy hint.
- [ ] **Intrinsic ChArUco:** switch board type to ChArUco, matching params → detection works with the board partially at frame edges (advantage over checkerboard).
- [ ] **Extrinsic:** select all 4 cameras → all previews live + sync spread shown; 세션 시작 (array, ring off). Hold board in the 0-1 overlap → Sync Capture → verdict shows `covered_pairs` includes 0-1, sync spread small; 저장 → `pair_counts` for 0-1 increments, `shot_000/` written with `detections.json`. Repeat for 1-2 and 2-3. Confirm pair-coverage display flags under-filled pairs. Turn on 링 배열 and confirm the (0,3) pair appears.
- [ ] **Sync sanity:** confirm extrinsic capture uses `frame_sync=1` (spread ms in report is small, matching Mode 2 behavior).
- [ ] **Regression:** Modes 1 & 2 still work (previews, capture, save unaffected).
- [ ] Run `.venv/bin/python -m pytest -v` once more → all green.

---

## Verification Summary

- **Automated (no hardware):** `.venv/bin/python -m pytest -v` — `test_calib_board.py`, `test_calib_quality.py` (pure logic), `test_calib_detect.py` (cv2 on synthetic board). All green.
- **End-to-end (hardware):** Task 11 checklist — intrinsic gate/save/coverage, ChArUco, extrinsic synced capture + pair coverage + ring, no Mode 1/2 regression.
- **Success criteria:** failing shots are un-saveable with a correct reason; passing shots save into per-mode session folders with JSON metadata; counts + coverage/pair guidance update live; extrinsic records which adjacent pairs saw the board per synchronized shot.

## Self-Review Notes
- Spec coverage: intrinsic (single-cam preview, board preset, validation pipeline, save-gate, count status, pose diversity) ✓; extrinsic (multi-cam synced, board preset, board scale via square_mm + world-frame clarification, pairwise guidance for 4 cams) ✓; both board types ✓.
- The `square_mm` field is the "실제 거리 고정" input for extrinsic (scale); the guide clarifies absolute room position isn't required for camera-to-camera extrinsics.
- Type consistency: `BoardConfig`, verdict/coverage/diversity dict shapes, and route JSON keys are referenced identically across tasks.
- No matrix computation (confirmed out of scope) — artifacts are structured for an offline calibration follow-up.
