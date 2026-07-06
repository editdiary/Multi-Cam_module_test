# e-con Multi-Camera 테스트 프로그램 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** e-con AR0234 4-camera 모듈을 웹에서 선택·촬영·저장하고 하드웨어 `frame_sync` 동기 촬영을 정량 검증하는 Flask 웹 도구를 구현한다.

**Architecture:** 캡처·이미지 처리는 GStreamer(Python `gi` + `appsink`, HW `nvvidconv`/`nvjpegenc`)로 수행하고, 동기 타임스탬프는 appsink 버퍼 PTS로 얻는다. 순수 로직(통계·파이프라인 문자열·파싱)과 하드웨어 의존 코드를 분리하고, Flask + 분리된 templates/static으로 3개 모드(단일/다중동기/캘리브레이션)를 제공한다.

**Tech Stack:** Python 3.10, GStreamer 1.20.3 (`gi`, `GstApp`, `nvvidconv`, `nvjpegenc`), Flask, `v4l2-ctl`, pytest.

## Global Constraints

- 플랫폼: NVIDIA Jetson, JetPack 6.1. 카메라: e-con AR0234 4대, `/dev/video0`~`/dev/video3`.
- 출력 포맷: **UYVY** 4:2:2. 해상도: `1280x720@120`, `1920x1080@65`, `1920x1200@60`.
- 동기화: V4L2 `frame_sync` (`0=Disable`, `1=30Hz`, `2=60Hz`), 설정은 `v4l2-ctl -c frame_sync=1 -d /dev/video<n>`.
- 신규 pip 의존성은 **`flask` 하나만** (+ 개발용 `pytest`). **cv2 사용 금지** — 이미지 처리는 GStreamer HW로 수행.
- 환경: `python3 -m venv --system-site-packages .venv` (numpy·GStreamer·`gi`는 시스템 재사용). 호스트 apt 무변경.
- 모든 명령은 저장소 루트(`Multi-Cam_module_test/`)에서 venv 활성화 후 실행.
- `ArduCam_Module_test/`는 구조 참고 전용 — 코드 재사용 금지.
- 파일은 관심사별로 작게 유지: `econ_cam/{gst_pipeline,capture,controls,stats,app}.py`.
- 설계 근거 상세: `docs/superpowers/specs/2026-07-06-econ-multicam-test-design.md`.

## File Structure

```
econ_cam/
  __init__.py          # 패키지 마커
  stats.py             # 타임스탬프 통계 (순수)
  gst_pipeline.py      # GStreamer 파이프라인 문자열 빌더 (순수)
  controls.py          # v4l2-ctl 래퍼 + 출력 파서
  capture.py           # gi 파이프라인 실행: Camera(단일/프리뷰), sync_capture(다중)
  app.py               # Flask 서버 + API 라우트 + base64 헬퍼
  templates/index.html # SPA
  static/app.js        # 프론트 로직
  static/style.css     # 스타일
run.py                 # 진입점
tests/
  test_env.py          # 환경 확인
  test_stats.py        # 통계 단위 테스트
  test_gst_pipeline.py # 파이프라인 문자열 단위 테스트
  test_controls.py     # v4l2-ctl 파서 단위 테스트
  test_capture.py      # 하드웨어 스모크 테스트 (카메라 있을 때만)
  test_app.py          # Flask API 테스트 (monkeypatch)
  test_frontend.py     # index.html 라우트 스모크 테스트
requirements.txt       # flask
captures/              # 저장 이미지 (.gitignore)
```

---

## Task 1: 프로젝트 스캐폴드 & 환경

**Files:**
- Create: `econ_cam/__init__.py`, `requirements.txt`, `tests/test_env.py`
- Modify: `.gitignore` (captures/ 추가)

**Interfaces:**
- Consumes: 없음
- Produces: `econ_cam` 임포트 가능한 패키지, venv 환경, pytest 실행 가능

- [ ] **Step 1: 패키지/디렉터리 생성**

```bash
cd Multi-Cam_module_test   # 저장소 루트로 이동
mkdir -p econ_cam/templates econ_cam/static tests captures
touch econ_cam/__init__.py
```

- [ ] **Step 2: `requirements.txt` 작성**

`requirements.txt`:
```
flask
```

- [ ] **Step 3: `.gitignore`에 captures/ 추가**

Run:
```bash
grep -q '^captures/' .gitignore || printf '\n# Captured images\ncaptures/\n' >> .gitignore
```

- [ ] **Step 4: venv 생성 및 의존성 설치**

Run:
```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install flask pytest
```
Expected: flask, pytest 설치 성공.

- [ ] **Step 5: 환경 확인 테스트 작성**

`tests/test_env.py`:
```python
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
    assert flask.__version__


def test_package_importable():
    import econ_cam
    assert econ_cam is not None
```

- [ ] **Step 6: 테스트 실행 (통과 확인)**

Run: `source .venv/bin/activate && python -m pytest tests/test_env.py -v`
Expected: 4 passed. (venv가 `--system-site-packages`라 시스템 `gi`를 임포트)

- [ ] **Step 7: 커밋**

```bash
git add econ_cam/__init__.py requirements.txt tests/test_env.py .gitignore
git commit -m "chore: scaffold econ_cam package and venv environment"
```

---

## Task 2: `stats.py` — 타임스탬프 통계

**Files:**
- Create: `econ_cam/stats.py`, `tests/test_stats.py`

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces: `timestamp_stats(timestamps: dict[int, float]) -> dict` — 반환 키:
  `per_camera` {dev: rel_ms}, `spread_ms` float, `std_ms` float(모집단 표준편차), `ref_dev` int|None

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_stats.py`:
```python
import math

from econ_cam.stats import timestamp_stats


def test_empty():
    r = timestamp_stats({})
    assert r == {"per_camera": {}, "spread_ms": 0.0, "std_ms": 0.0, "ref_dev": None}


def test_single_camera():
    r = timestamp_stats({2: 10.5})
    assert r["per_camera"] == {2: 0.0}
    assert r["spread_ms"] == 0.0
    assert r["std_ms"] == 0.0
    assert r["ref_dev"] == 2


def test_multi_camera_relative_and_spread():
    # 초 단위 입력, ms 단위 상대값 출력
    r = timestamp_stats({0: 10.000, 1: 10.002, 2: 10.001})
    assert r["ref_dev"] == 0
    assert r["per_camera"][0] == 0.0
    assert math.isclose(r["per_camera"][1], 2.0, abs_tol=1e-6)
    assert math.isclose(r["per_camera"][2], 1.0, abs_tol=1e-6)
    assert math.isclose(r["spread_ms"], 2.0, abs_tol=1e-6)
    # 모집단 표준편차 pstdev([0,2,1]) = sqrt(2/3)
    assert math.isclose(r["std_ms"], math.sqrt(2 / 3), abs_tol=1e-6)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'econ_cam.stats'`

- [ ] **Step 3: 구현**

`econ_cam/stats.py`:
```python
"""동기 캡처 타임스탬프 통계 (순수 함수)."""

import statistics


def timestamp_stats(timestamps):
    """{dev: ts_seconds} -> 통계 dict.

    Returns:
        {
          "per_camera": {dev: rel_ms},   # 최소 타임스탬프 기준 상대값(ms)
          "spread_ms": float,            # max - min (ms)
          "std_ms": float,               # 모집단 표준편차 (ms)
          "ref_dev": int | None,         # 기준(최소) 카메라
        }
    """
    if not timestamps:
        return {"per_camera": {}, "spread_ms": 0.0, "std_ms": 0.0, "ref_dev": None}

    ref_dev = min(timestamps, key=timestamps.get)
    ref = timestamps[ref_dev]
    per_camera = {dev: (ts - ref) * 1000.0 for dev, ts in timestamps.items()}
    values = list(per_camera.values())
    spread_ms = max(values) - min(values)
    std_ms = statistics.pstdev(values) if len(values) > 1 else 0.0
    return {
        "per_camera": per_camera,
        "spread_ms": spread_ms,
        "std_ms": std_ms,
        "ref_dev": ref_dev,
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_stats.py -v`
Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/stats.py tests/test_stats.py
git commit -m "feat: add timestamp_stats for sync verification"
```

---

## Task 3: `gst_pipeline.py` — 파이프라인 문자열 빌더

**Files:**
- Create: `econ_cam/gst_pipeline.py`, `tests/test_gst_pipeline.py`

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces:
  - `preview_pipeline(dev: int, width: int, height: int, sink_name: str = "sink") -> str`
  - `sync_pipeline(devs: list[int], width: int, height: int) -> str`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_gst_pipeline.py`:
```python
from econ_cam.gst_pipeline import preview_pipeline, sync_pipeline


def test_preview_pipeline_contains_device_and_caps():
    p = preview_pipeline(0, 1920, 1080)
    assert "v4l2src device=/dev/video0" in p
    assert "format=UYVY" in p
    assert "width=1920,height=1080" in p
    assert "nvvidconv" in p
    assert "nvjpegenc" in p
    assert "appsink name=sink" in p


def test_preview_pipeline_custom_sink_name():
    p = preview_pipeline(3, 1280, 720, sink_name="sink3")
    assert "device=/dev/video3" in p
    assert "appsink name=sink3" in p


def test_sync_pipeline_has_one_branch_per_device():
    p = sync_pipeline([0, 2], 1920, 1080)
    assert p.count("v4l2src") == 2
    assert "device=/dev/video0" in p
    assert "device=/dev/video2" in p
    assert "appsink name=sink0" in p
    assert "appsink name=sink2" in p
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_gst_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'econ_cam.gst_pipeline'`

- [ ] **Step 3: 구현**

`econ_cam/gst_pipeline.py`:
```python
"""GStreamer 파이프라인 문자열 빌더 (순수 함수).

실기 검증된 파이프라인:
  v4l2src ! video/x-raw,format=UYVY ! nvvidconv ! nvjpegenc ! image/jpeg ! appsink
"""


def _branch(dev, width, height, sink_name):
    return (
        f"v4l2src device=/dev/video{dev} "
        f"! video/x-raw,format=UYVY,width={width},height={height} "
        f"! nvvidconv ! nvjpegenc ! image/jpeg "
        f"! appsink name={sink_name} max-buffers=1 drop=true sync=false"
    )


def preview_pipeline(dev, width, height, sink_name="sink"):
    """단일 카메라 프리뷰/캡처 파이프라인."""
    return _branch(dev, width, height, sink_name)


def sync_pipeline(devs, width, height):
    """다중 카메라 동기 캡처 — 단일 파이프라인에 카메라별 브랜치(공유 클럭).

    각 브랜치의 appsink 이름은 sink{dev}.
    """
    return "   ".join(_branch(d, width, height, f"sink{d}") for d in devs)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_gst_pipeline.py -v`
Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/gst_pipeline.py tests/test_gst_pipeline.py
git commit -m "feat: add GStreamer pipeline string builders"
```

---

## Task 4: `controls.py` — v4l2-ctl 래퍼 & 파서

**Files:**
- Create: `econ_cam/controls.py`, `tests/test_controls.py`

**Interfaces:**
- Consumes: 없음
- Produces (순수 파서):
  - `parse_card_type(info_text: str) -> str`
  - `parse_resolutions(text: str) -> list[tuple[int, int]]`
  - `parse_controls(text: str) -> dict[str, dict]`  # {name: {"type","min","max","step","default","value"}}
- Produces (subprocess 래퍼):
  - `detect_cameras() -> list[dict]`  # [{"dev","name","label"}]
  - `list_resolutions(dev: int) -> list[tuple[int,int]]`
  - `get_controls(dev: int) -> dict`
  - `set_control(dev: int, name: str, value) -> bool`
  - `set_frame_sync(dev: int, mode: int) -> bool`

- [ ] **Step 1: 실패하는 테스트 작성 (실제 하드웨어 출력 샘플 사용)**

`tests/test_controls.py`:
```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_controls.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'econ_cam.controls'`

- [ ] **Step 3: 구현**

`econ_cam/controls.py`:
```python
"""V4L2 카메라 감지 및 컨트롤 (v4l2-ctl subprocess 래퍼 + 출력 파서)."""

import os
import re
import subprocess

_CTRL_RE = re.compile(r"^\s*(\w+)\s+0x[0-9a-fA-F]+\s+\((\w+)\)\s*:\s*(.*)$")
_INT_FIELDS = ("min", "max", "step", "default", "value")


# --- 순수 파서 -----------------------------------------------------------

def parse_card_type(info_text):
    """v4l2-ctl --info 출력에서 'Card type' 값을 추출."""
    for line in info_text.splitlines():
        if "Card type" in line:
            return line.split(":", 1)[1].strip()
    return "Unknown"


def parse_resolutions(text):
    """--list-formats-ext 출력에서 'Size: Discrete WxH'를 순서 유지·중복 제거로 추출."""
    res = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Size: Discrete"):
            wh = line.split()[-1]
            w, h = wh.split("x")
            item = (int(w), int(h))
            if item not in res:
                res.append(item)
    return res


def parse_controls(text):
    """v4l2-ctl -L 출력에서 컨트롤 목록을 파싱.

    각 컨트롤: {"type": str, "min"/"max"/"step"/"default"/"value": int(있을 때)}.
    메뉴 옵션 서브라인은 무시한다.
    """
    controls = {}
    for line in text.splitlines():
        m = _CTRL_RE.match(line)
        if not m:
            continue
        name, ctype, rest = m.group(1), m.group(2), m.group(3)
        entry = {"type": ctype}
        fields = {}
        for token in rest.split():
            if "=" in token:
                k, v = token.split("=", 1)
                fields[k] = v
        for k in _INT_FIELDS:
            if k in fields:
                try:
                    entry[k] = int(fields[k])
                except ValueError:
                    entry[k] = fields[k]
        controls[name] = entry
    return controls


# --- subprocess 래퍼 -----------------------------------------------------

def _run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=5).stdout


def detect_cameras():
    """/dev/video0..15 중 카드 이름에 'ar0234'가 포함된 캡처 노드를 반환."""
    cams = []
    for i in range(16):
        if not os.path.exists(f"/dev/video{i}"):
            continue
        card = parse_card_type(_run(["v4l2-ctl", "-d", f"/dev/video{i}", "--info"]))
        if "ar0234" in card.lower():
            cams.append({"dev": i, "name": card, "label": f"Camera {i} ({card})"})
    return cams


def list_resolutions(dev):
    return parse_resolutions(_run(["v4l2-ctl", "-d", f"/dev/video{dev}", "--list-formats-ext"]))


def get_controls(dev):
    return parse_controls(_run(["v4l2-ctl", "-d", f"/dev/video{dev}", "-L"]))


def set_control(dev, name, value):
    result = subprocess.run(
        ["v4l2-ctl", "-d", f"/dev/video{dev}", "-c", f"{name}={value}"],
        capture_output=True, text=True, timeout=5,
    )
    return result.returncode == 0


def set_frame_sync(dev, mode):
    """frame_sync 설정: 0=Disable, 1=30Hz, 2=60Hz."""
    return set_control(dev, "frame_sync", mode)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_controls.py -v`
Expected: 5 passed.

- [ ] **Step 5: (하드웨어) 감지 동작 확인**

Run: `source .venv/bin/activate && python -c "from econ_cam import controls; print(controls.detect_cameras())"`
Expected: 4개 카메라 목록 출력 (`dev` 0~3, name에 ar0234 포함).

- [ ] **Step 6: 커밋**

```bash
git add econ_cam/controls.py tests/test_controls.py
git commit -m "feat: add v4l2-ctl wrappers and output parsers"
```

---

## Task 5: `capture.py` — GStreamer 캡처 (Camera + sync_capture)

**Files:**
- Create: `econ_cam/capture.py`, `tests/test_capture.py`

**Interfaces:**
- Consumes: `gst_pipeline.preview_pipeline`, `gst_pipeline.sync_pipeline`, `controls.set_frame_sync`, `stats.timestamp_stats`
- Produces:
  - `class Camera(dev, width, height)`: `.start()`, `.latest_jpeg() -> bytes|None`, `.capture() -> (bytes, float)`, `.stop()`
  - `sync_capture(devs, width, height, sync_mode=1) -> {"images": {dev: bytes}, "timestamps": {dev: float}, "stats": dict}`

- [ ] **Step 1: 하드웨어 스모크 테스트 작성**

`tests/test_capture.py`:
```python
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.path.exists("/dev/video0"), reason="카메라 하드웨어 없음"
)


def test_camera_capture_returns_jpeg():
    from econ_cam.capture import Camera

    cam = Camera(0, 1920, 1080)
    cam.start()
    try:
        jpeg, pts = cam.capture()
    finally:
        cam.stop()
    assert jpeg[:2] == b"\xff\xd8"  # JPEG SOI 마커
    assert pts > 0


def test_camera_latest_jpeg():
    from econ_cam.capture import Camera

    cam = Camera(0, 1280, 720)
    cam.start()
    try:
        jpeg = cam.latest_jpeg()
    finally:
        cam.stop()
    assert jpeg is not None
    assert jpeg[:2] == b"\xff\xd8"


@pytest.mark.skipif(not os.path.exists("/dev/video1"), reason="두 번째 카메라 없음")
def test_sync_capture_two_cameras():
    from econ_cam.capture import sync_capture

    result = sync_capture([0, 1], 1280, 720, sync_mode=1)
    assert set(result["images"].keys()) == {0, 1}
    for jpeg in result["images"].values():
        assert jpeg[:2] == b"\xff\xd8"
    assert "spread_ms" in result["stats"]
    assert "std_ms" in result["stats"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'econ_cam.capture'`

- [ ] **Step 3: 구현**

`econ_cam/capture.py`:
```python
"""GStreamer 기반 카메라 캡처 (Python gi + appsink).

- Camera: 단일 카메라 파이프라인 (프리뷰 + 단일 캡처)
- sync_capture: 단일 공유클럭 파이프라인으로 다중 카메라 동기 캡처

appsink 버퍼 PTS(ns)를 초 단위로 변환해 타임스탬프로 사용한다.
다중 동기 캡처는 각 appsink(drop=true, max-buffers=1)에서 최신 버퍼를 순차 pull한다.
frame_sync가 30Hz(33ms)로 락되어 있고 순차 pull은 수 ms 내에 끝나므로 같은 프레임
주기의 버퍼를 얻는다(공유 클럭으로 PTS 비교 가능).
"""

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")
from gi.repository import Gst  # noqa: E402

from econ_cam import controls, gst_pipeline, stats  # noqa: E402

Gst.init(None)

_PULL_TIMEOUT_S = 3.0


def _pull(sink, timeout_s):
    """appsink에서 (jpeg_bytes, pts_seconds) 하나 pull. 실패 시 None."""
    sample = sink.emit("try-pull-sample", int(timeout_s * Gst.SECOND))
    if sample is None:
        return None
    buf = sample.get_buffer()
    data = buf.extract_dup(0, buf.get_size())
    pts = buf.pts / 1e9
    return data, pts


class Camera:
    """단일 카메라 GStreamer 파이프라인 (프리뷰 + 단일 캡처)."""

    def __init__(self, dev, width, height):
        self.dev = dev
        self.width = width
        self.height = height
        self._pipeline = None
        self._sink = None

    def start(self):
        desc = gst_pipeline.preview_pipeline(self.dev, self.width, self.height)
        self._pipeline = Gst.parse_launch(desc)
        self._sink = self._pipeline.get_by_name("sink")
        self._pipeline.set_state(Gst.State.PLAYING)

    def latest_jpeg(self):
        result = _pull(self._sink, 2.0)
        return result[0] if result else None

    def capture(self):
        result = _pull(self._sink, _PULL_TIMEOUT_S)
        if result is None:
            raise RuntimeError(f"capture timeout on /dev/video{self.dev}")
        return result

    def stop(self):
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._sink = None


def sync_capture(devs, width, height, sync_mode=1):
    """다중 카메라 동기 캡처.

    1) 선택 카메라 전체에 frame_sync 설정
    2) 단일 공유클럭 파이프라인 실행
    3) 각 appsink에서 1프레임 pull (jpeg, pts)
    4) 통계 계산
    """
    for d in devs:
        controls.set_frame_sync(d, sync_mode)

    desc = gst_pipeline.sync_pipeline(devs, width, height)
    pipeline = Gst.parse_launch(desc)
    pipeline.set_state(Gst.State.PLAYING)

    images = {}
    timestamps = {}
    try:
        for d in devs:
            sink = pipeline.get_by_name(f"sink{d}")
            result = _pull(sink, _PULL_TIMEOUT_S)
            if result is None:
                raise RuntimeError(f"sync capture timeout on /dev/video{d}")
            images[d], timestamps[d] = result
    finally:
        pipeline.set_state(Gst.State.NULL)

    return {
        "images": images,
        "timestamps": timestamps,
        "stats": stats.timestamp_stats(timestamps),
    }
```

- [ ] **Step 4: 테스트 통과 확인 (하드웨어)**

Run: `source .venv/bin/activate && python -m pytest tests/test_capture.py -v`
Expected: 3 passed (카메라 0,1 존재 시).

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/capture.py tests/test_capture.py
git commit -m "feat: add GStreamer Camera and sync_capture"
```

---

## Task 6: `app.py` + `run.py` — Flask API & 진입점

**Files:**
- Create: `econ_cam/app.py`, `run.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `capture.Camera`, `capture.sync_capture`, `controls.*`
- Produces:
  - `jpeg_to_data_uri(jpeg_bytes: bytes) -> str`
  - `create_app(width=1920, height=1080) -> Flask`
  - 라우트: `/`, `/api/cameras`, `/api/cameras/refresh`, `/api/stream/<int:dev>/mjpeg`,
    `/api/stream/stop`, `/api/capture`, `/api/save`, `/api/resolutions`, `/api/resolution`,
    `/api/params` (GET/POST), `/api/frame_sync`

- [ ] **Step 1: 실패하는 테스트 작성 (monkeypatch로 하드웨어 대체)**

`tests/test_app.py`:
```python
import base64
import glob
import os

from econ_cam import app as app_module


def test_jpeg_to_data_uri():
    uri = app_module.jpeg_to_data_uri(b"\xff\xd8")
    assert uri == "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8").decode()


def test_capture_multi(monkeypatch):
    fake = {
        "images": {0: b"\xff\xd8zero", 1: b"\xff\xd8one"},
        "timestamps": {0: 10.000, 1: 10.002},
        "stats": {"per_camera": {0: 0.0, 1: 2.0},
                  "spread_ms": 2.0, "std_ms": 1.0, "ref_dev": 0},
    }
    monkeypatch.setattr(app_module.capture, "sync_capture", lambda *a, **k: fake)
    client = app_module.create_app().test_client()
    resp = client.post("/api/capture", json={"mode": "multi", "devices": [0, 1]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body["images"].keys()) == {"0", "1"}
    assert body["images"]["0"].startswith("data:image/jpeg;base64,")
    assert body["stats"]["spread_ms"] == 2.0
    assert body["stats"]["per_camera"]["1"] == 2.0


def test_save_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "CAPTURE_DIR", str(tmp_path))
    fake = {
        "images": {0: b"\xff\xd8AAA"},
        "timestamps": {0: 1.0},
        "stats": {"per_camera": {0: 0.0}, "spread_ms": 0.0, "std_ms": 0.0, "ref_dev": 0},
    }
    monkeypatch.setattr(app_module.capture, "sync_capture", lambda *a, **k: fake)
    client = app_module.create_app().test_client()
    client.post("/api/capture", json={"mode": "multi", "devices": [0]})
    resp = client.post("/api/save")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    jpgs = glob.glob(os.path.join(str(tmp_path), "*", "video0.jpg"))
    reports = glob.glob(os.path.join(str(tmp_path), "*", "sync_report.json"))
    assert len(jpgs) == 1
    assert len(reports) == 1


def test_cameras_route(monkeypatch):
    monkeypatch.setattr(app_module.controls, "detect_cameras",
                        lambda: [{"dev": 0, "name": "ar0234", "label": "Camera 0"}])
    client = app_module.create_app().test_client()
    body = client.get("/api/cameras").get_json()
    assert body[0]["dev"] == 0
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'econ_cam.app'`

- [ ] **Step 3: `app.py` 구현**

`econ_cam/app.py`:
```python
"""Flask 웹 서버 + API 라우트."""

import base64
import json
import os
import threading
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from econ_cam import capture, controls

CAPTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "captures")


def jpeg_to_data_uri(jpeg_bytes):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def _json_stats(stats):
    """통계 dict를 JSON 직렬화 가능하게(키를 str로) 변환."""
    return {
        "per_camera": {str(k): round(v, 4) for k, v in stats["per_camera"].items()},
        "spread_ms": round(stats["spread_ms"], 4),
        "std_ms": round(stats["std_ms"], 4),
        "ref_dev": stats["ref_dev"],
    }


def create_app(width=1920, height=1080):
    app = Flask(__name__)
    state = {
        "cameras": [],
        "streams": {},     # {dev: capture.Camera} 프리뷰 파이프라인
        "last": {},        # {dev: jpeg_bytes} 최근 캡처
        "last_stats": None,
        "width": width,
        "height": height,
        "lock": threading.Lock(),
    }

    def stop_streams():
        for cam in state["streams"].values():
            cam.stop()
        state["streams"].clear()

    def get_or_start_stream(dev):
        cam = state["streams"].get(dev)
        if cam is None:
            cam = capture.Camera(dev, state["width"], state["height"])
            cam.start()
            state["streams"][dev] = cam
        return cam

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/cameras")
    def api_cameras():
        if not state["cameras"]:
            state["cameras"] = controls.detect_cameras()
        return jsonify(state["cameras"])

    @app.route("/api/cameras/refresh", methods=["POST"])
    def api_cameras_refresh():
        with state["lock"]:
            stop_streams()
            state["cameras"] = controls.detect_cameras()
        return jsonify(state["cameras"])

    @app.route("/api/stream/<int:dev>/mjpeg")
    def api_stream(dev):
        with state["lock"]:
            cam = get_or_start_stream(dev)

        def gen():
            while True:
                jpeg = cam.latest_jpeg()
                if jpeg is None:
                    break
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")

        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/api/stream/stop", methods=["POST"])
    def api_stream_stop():
        with state["lock"]:
            stop_streams()
        return jsonify({"ok": True})

    @app.route("/api/capture", methods=["POST"])
    def api_capture():
        data = request.get_json(force=True)
        mode = data.get("mode", "single")
        with state["lock"]:
            if mode == "single":
                dev = int(data["devices"][0])
                cam = get_or_start_stream(dev)
                jpeg, _ = cam.capture()
                state["last"] = {dev: jpeg}
                state["last_stats"] = None
                return jsonify({"images": {str(dev): jpeg_to_data_uri(jpeg)}})
            # multi: 프리뷰가 device를 점유하면 동기 파이프라인이 실패하므로 먼저 정리
            stop_streams()
            devs = [int(d) for d in data["devices"]]
            sync_mode = int(data.get("sync_mode", 1))
            result = capture.sync_capture(devs, state["width"], state["height"], sync_mode)
            state["last"] = result["images"]
            state["last_stats"] = result["stats"]
            images = {str(d): jpeg_to_data_uri(j) for d, j in result["images"].items()}
            return jsonify({"images": images, "stats": _json_stats(result["stats"])})

    @app.route("/api/save", methods=["POST"])
    def api_save():
        if not state["last"]:
            return jsonify({"ok": False, "error": "no capture"}), 400
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        outdir = os.path.join(CAPTURE_DIR, ts)
        os.makedirs(outdir, exist_ok=True)
        for dev, jpeg in state["last"].items():
            with open(os.path.join(outdir, f"video{dev}.jpg"), "wb") as f:
                f.write(jpeg)
        if state["last_stats"] is not None:
            with open(os.path.join(outdir, "sync_report.json"), "w") as f:
                json.dump(_json_stats(state["last_stats"]), f, indent=2)
        return jsonify({"ok": True, "path": outdir})

    @app.route("/api/resolutions")
    def api_resolutions():
        dev = int(request.args["dev"])
        return jsonify(controls.list_resolutions(dev))

    @app.route("/api/resolution", methods=["POST"])
    def api_set_resolution():
        data = request.get_json(force=True)
        with state["lock"]:
            state["width"] = int(data["width"])
            state["height"] = int(data["height"])
            stop_streams()
        return jsonify({"ok": True, "width": state["width"], "height": state["height"]})

    @app.route("/api/params")
    def api_get_params():
        dev = int(request.args["dev"])
        return jsonify(controls.get_controls(dev))

    @app.route("/api/params", methods=["POST"])
    def api_set_params():
        data = request.get_json(force=True)
        ok = controls.set_control(int(data["dev"]), data["name"], data["value"])
        return jsonify({"ok": ok})

    @app.route("/api/frame_sync", methods=["POST"])
    def api_frame_sync():
        data = request.get_json(force=True)
        mode = int(data["mode"])
        results = {int(d): controls.set_frame_sync(int(d), mode) for d in data["devices"]}
        return jsonify({"ok": all(results.values())})

    return app
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_app.py -v`
Expected: 4 passed. (`/` 라우트는 템플릿이 아직 없어 테스트하지 않음 — Task 7에서 검증)

- [ ] **Step 5: `run.py` 구현**

`run.py`:
```python
#!/usr/bin/env python3
"""e-con Multi-Cam 테스트 웹 서버 진입점.

사용법:
  python3 run.py
  python3 run.py --port 8888 --width 1920 --height 1080
"""

import argparse

from econ_cam.app import create_app


def main():
    parser = argparse.ArgumentParser(description="e-con Multi-Cam Test 웹 서버")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()

    app = create_app(args.width, args.height)
    # MJPEG 스트리밍과 동시 요청 처리를 위해 threaded=True
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 커밋**

```bash
git add econ_cam/app.py run.py tests/test_app.py
git commit -m "feat: add Flask API server and entry point"
```

---

## Task 7: 프론트엔드 (SPA) & 엔드투엔드 검증

**Files:**
- Create: `econ_cam/templates/index.html`, `econ_cam/static/app.js`, `econ_cam/static/style.css`, `tests/test_frontend.py`

**Interfaces:**
- Consumes: Task 6의 모든 `/api/*` 라우트, `/` 라우트
- Produces: 3개 모드 탭 SPA (단일/다중동기/캘리브레이션)

- [ ] **Step 1: 실패하는 라우트 스모크 테스트 작성**

`tests/test_frontend.py`:
```python
from econ_cam.app import create_app


def test_index_served():
    client = create_app().test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "다중 동기 촬영" in html
    assert "캘리브레이션" in html
    assert "/static/app.js" in html
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_frontend.py -v`
Expected: FAIL — `TemplateNotFound: index.html` (500) 또는 assertion 실패.

- [ ] **Step 3: `index.html` 구현**

`econ_cam/templates/index.html`:
```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>e-con Multi-Cam Test</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <h1>e-con Multi-Cam Test</h1>
    <button id="refresh">카메라 재감지</button>
  </header>

  <nav class="tabs">
    <button class="tab active" data-mode="single">단일 촬영</button>
    <button class="tab" data-mode="multi">다중 동기 촬영</button>
    <button class="tab" data-mode="calib">캘리브레이션</button>
  </nav>

  <section id="single" class="mode active">
    <div class="controls">
      <select id="single-cam"></select>
      <button id="single-capture">Capture</button>
      <button id="single-save">Save</button>
    </div>
    <div class="view">
      <img id="single-preview" alt="preview">
      <img id="single-still" alt="still" hidden>
    </div>
  </section>

  <section id="multi" class="mode">
    <div class="controls">
      <div id="multi-cams" class="checkboxes"></div>
      <button id="multi-capture">Sync Capture</button>
      <button id="multi-save">Save All</button>
    </div>
    <div id="multi-grid" class="grid"></div>
    <table id="sync-stats"></table>
  </section>

  <section id="calib" class="mode">
    <p class="placeholder">캘리브레이션 기능은 추후 업데이트 예정입니다.</p>
  </section>

  <div id="toast"></div>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: `app.js` 구현**

`econ_cam/static/app.js`:
```javascript
"use strict";

const api = (p, opts) => fetch(p, opts).then((r) => r.json());
const jsonPost = (p, body) =>
  api(p, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

let cameras = [];

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2500);
}

async function stopStreams() {
  document.getElementById("single-preview").src = "";
  await fetch("/api/stream/stop", { method: "POST" });
}

function setMode(mode) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.mode === mode)
  );
  document.querySelectorAll(".mode").forEach((s) =>
    s.classList.toggle("active", s.id === mode)
  );
  stopStreams().then(() => {
    if (mode === "single") startSinglePreview();
  });
}

async function loadCameras() {
  cameras = await api("/api/cameras");
  document.getElementById("single-cam").innerHTML = cameras
    .map((c) => `<option value="${c.dev}">${c.label}</option>`)
    .join("");
  document.getElementById("multi-cams").innerHTML = cameras
    .map(
      (c) =>
        `<label><input type="checkbox" value="${c.dev}" checked> ${c.label}</label>`
    )
    .join("");
}

function startSinglePreview() {
  const dev = document.getElementById("single-cam").value;
  if (!dev) return;
  const still = document.getElementById("single-still");
  still.hidden = true;
  const img = document.getElementById("single-preview");
  img.hidden = false;
  img.src = `/api/stream/${dev}/mjpeg?t=${Date.now()}`;
}

async function singleCapture() {
  const dev = document.getElementById("single-cam").value;
  const data = await jsonPost("/api/capture", { mode: "single", devices: [dev] });
  const still = document.getElementById("single-still");
  still.src = data.images[dev];
  still.hidden = false;
  document.getElementById("single-preview").hidden = true;
}

async function save() {
  const r = await api("/api/save", { method: "POST" });
  toast(r.ok ? `저장됨: ${r.path}` : `저장 실패: ${r.error}`);
}

async function multiCapture() {
  const devs = [...document.querySelectorAll("#multi-cams input:checked")].map(
    (c) => c.value
  );
  if (!devs.length) {
    toast("카메라를 선택하세요");
    return;
  }
  toast("동기 촬영 중...");
  const data = await jsonPost("/api/capture", {
    mode: "multi",
    devices: devs,
    sync_mode: 1,
  });
  document.getElementById("multi-grid").innerHTML = Object.entries(data.images)
    .map(
      ([dev, uri]) =>
        `<figure><img src="${uri}"><figcaption>video${dev}</figcaption></figure>`
    )
    .join("");
  const s = data.stats;
  const rows = Object.entries(s.per_camera)
    .map(
      ([dev, ms]) => `<tr><td>video${dev}</td><td>${ms.toFixed(3)} ms</td></tr>`
    )
    .join("");
  document.getElementById("sync-stats").innerHTML =
    `<tr><th>카메라</th><th>상대 타임스탬프</th></tr>${rows}` +
    `<tr class="summary"><td>최대 편차 (max−min)</td><td>${s.spread_ms.toFixed(
      3
    )} ms</td></tr>` +
    `<tr class="summary"><td>표준편차</td><td>${s.std_ms.toFixed(3)} ms</td></tr>`;
}

document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => setMode(t.dataset.mode))
);
document
  .getElementById("single-cam")
  .addEventListener("change", startSinglePreview);
document
  .getElementById("single-capture")
  .addEventListener("click", singleCapture);
document.getElementById("single-save").addEventListener("click", save);
document.getElementById("multi-capture").addEventListener("click", multiCapture);
document.getElementById("multi-save").addEventListener("click", save);
document.getElementById("refresh").addEventListener("click", async () => {
  await fetch("/api/cameras/refresh", { method: "POST" });
  await loadCameras();
  toast("재감지 완료");
});

loadCameras().then(() => setMode("single"));
```

- [ ] **Step 5: `style.css` 구현**

`econ_cam/static/style.css`:
```css
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, sans-serif;
  background: #1a1a1a;
  color: #eee;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #111;
}
h1 { font-size: 18px; margin: 0; }
button {
  background: #2d7;
  color: #062;
  border: 0;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}
button:hover { filter: brightness(1.1); }
.tabs { display: flex; gap: 4px; padding: 12px 20px 0; }
.tab {
  background: #333;
  color: #ccc;
  border-radius: 6px 6px 0 0;
}
.tab.active { background: #2d7; color: #062; }
.mode { display: none; padding: 20px; }
.mode.active { display: block; }
.controls {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
select {
  padding: 8px;
  border-radius: 6px;
  background: #333;
  color: #eee;
  border: 1px solid #555;
}
.checkboxes { display: flex; gap: 16px; flex-wrap: wrap; }
.checkboxes label { display: flex; gap: 6px; align-items: center; }
.view img { max-width: 100%; border-radius: 8px; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.grid figure { margin: 0; }
.grid img { width: 100%; border-radius: 8px; }
.grid figcaption { text-align: center; padding: 4px; color: #aaa; }
#sync-stats {
  margin-top: 20px;
  border-collapse: collapse;
  min-width: 320px;
}
#sync-stats th, #sync-stats td {
  border: 1px solid #444;
  padding: 8px 14px;
  text-align: left;
}
#sync-stats .summary td { font-weight: 700; background: #262; }
.placeholder { color: #888; font-size: 16px; }
#toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: #333;
  padding: 12px 24px;
  border-radius: 8px;
  opacity: 0;
  transition: opacity 0.3s;
  pointer-events: none;
}
#toast.show { opacity: 1; }
```

- [ ] **Step 6: 라우트 스모크 테스트 통과 확인**

Run: `source .venv/bin/activate && python -m pytest tests/test_frontend.py -v`
Expected: 1 passed.

- [ ] **Step 7: 전체 테스트 실행**

Run: `source .venv/bin/activate && python -m pytest -v`
Expected: 모든 테스트 통과 (하드웨어 있으면 test_capture 포함).

- [ ] **Step 8: 엔드투엔드 수동 검증**

Run: `source .venv/bin/activate && python run.py --width 1280 --height 720`
브라우저에서 `http://<jetson-ip>:8888/` 접속 후 확인:
- **단일 촬영** 탭: 카메라 선택 → 라이브 프리뷰 표시 → Capture → 정지 이미지 → Save 시 `captures/<ts>/videoN.jpg` 생성
- **다중 동기 촬영** 탭: 카메라 여러 대 체크 → Sync Capture → 이미지 grid + 타임스탬프/최대편차/표준편차 표시 → Save All 시 `captures/<ts>/`에 이미지들 + `sync_report.json` 생성
- **캘리브레이션** 탭: placeholder 문구 표시
- (동기 실효성) `frame_sync=1`일 때 표준편차/최대편차가 작게 나오는지 확인

- [ ] **Step 9: 커밋**

```bash
git add econ_cam/templates/index.html econ_cam/static/app.js econ_cam/static/style.css tests/test_frontend.py
git commit -m "feat: add SPA frontend with three test modes"
```

---

## 이번 계획에서 UI 미포함 (백엔드 API만 제공)

스펙에서 "(선택)"으로 표시된 다음 기능은 백엔드 엔드포인트(`/api/params`, `/api/resolutions`,
`/api/resolution`)만 구현하고 **프론트 UI는 후속**으로 둔다. 해상도는 당장 `run.py --width/--height`
CLI 플래그로 지정한다.
- exposure/gain 등 카메라 파라미터 조정 슬라이더
- 웹에서의 런타임 해상도 변경 위젯

## 검증 요약 (Success Criteria)

- **자동 (pytest, 하드웨어 불필요):** `test_env`, `test_stats`, `test_gst_pipeline`, `test_controls`, `test_app`, `test_frontend` 통과.
- **하드웨어 스모크:** `test_capture` — 실제 카메라에서 JPEG(SOI 마커) + PTS 획득.
- **수동 E2E:** 3개 모드 브라우저 동작, 동기 지표 표시, `frame_sync` ON이 OFF보다 편차 작음 확인.
