# e-con Multi-Camera 테스트 프로그램 — 설계 문서 (Design Spec)

- 작성일: 2026-07-06
- 상태: 구현 완료 (Mode 1·2·3). 이 문서는 초기 설계 기록이며, 일부 항목은 아래 갱신 노트로 대체됨.
- 대상 하드웨어: NVIDIA Jetson (JetPack 6.1), e-con systems AR0234 4-camera 모듈

> **갱신 노트 (2026-07-08):** Mode 3는 원 설계의 "UI 스켈레톤만"에서 **체커보드/ChArUco 이미지
> 수집 + 품질 검증**(Intrinsic 단일 / Extrinsic 다중 동기, 인접 쌍 커버리지)으로 구현되었다.
> 이를 위해 `cv2`(opencv-contrib-python, venv 전용)를 도입했다(원 설계 §10의 "cv2 필요 시 추가" 실행).
> 실제 K/extrinsic 행렬 **계산**은 여전히 범위 밖(오프라인 후속). 아래 Mode 3 관련 절(§2, §8.Mode 3, §9)은
> 이 노트로 갱신된 것으로 본다. 상세: `docs/superpowers/plans/2026-07-08-calibration-mode.md`, 사용법: `docs/USAGE.md`.

---

## 1. 목표 (Goal)

연결된 4대의 e-con AR0234 카메라를 웹 브라우저에서 자유롭게 선택·촬영·저장하고,
**하드웨어 `frame_sync` 기반 다중 카메라 동기 촬영이 제대로 되는지 정량적으로 검증**할 수 있는
Flask 웹 기반 카메라 테스트 도구를 만든다.

## 2. 범위 (Scope)

### 이번 구현에 포함
- **Mode 1 — 단일 카메라 촬영 테스트**: 라이브 프리뷰 + 캡처 + 저장
- **Mode 2 — 다중 카메라 동기 촬영 테스트**: `frame_sync` HW 동기 촬영 + 타임스탬프 정량 검증 + 저장
- **Mode 3 — 캘리브레이션 모드**: UI 스켈레톤(레이아웃 + placeholder)만

### 이번 구현에서 제외 (별도 spec/plan으로 분리)
- **ROS2 패키지화**: ROS2 환경 세팅 및 기능 확정 후 별도 진행. 본 도구의 `econ_cam` 패키지는
  순수 Python으로 설계되어 향후 ROS2 워크스페이스/Docker에 그대로 이식 가능하도록 한다.
- **실제 캘리브레이션 연산**(intrinsic/extrinsic 계산): Mode 3는 이번엔 UI만.

## 3. 하드웨어 / 환경 사실 (탐색으로 확인됨)

| 항목 | 내용 |
|------|------|
| 카메라 | e-con AR0234 4대, `/dev/video0` ~ `/dev/video3`, `tegra-video`(CSI) 드라이버 |
| 출력 포맷 | **UYVY** 4:2:2 (모듈에서 디베이어링 완료 → SW demosaic 불필요), NV16도 지원 |
| 해상도/FPS | `1280x720@120`, `1920x1080@65`, `1920x1200@60` (Discrete) |
| 동기화 컨트롤 | V4L2 `frame_sync` (menu): `0=Disable`, `1=Frame Sync 30Hz`, `2=Frame Sync 60Hz` |
| 동기 설정 명령 | 공식 가이드: `v4l2-ctl -c frame_sync=1 -d /dev/video<n>` |
| 카메라 컨트롤 | exposure(auto/manual/ROI), exposure_time_absolute, gain, brightness, contrast, saturation, gamma, white_balance(auto/temp), denoise, sharpness, h/v flip |
| 기존 설치 | `numpy` 1.21, GStreamer 1.20.3 + Python 바인딩(`gi`, `GstApp`), HW 플러그인(`nvvidconv`/`nvjpegenc`/`nvv4l2h264enc`) + SW `jpegenc`, `v4l2-ctl`, `media-ctl`, `python3` 3.10 |
| 미설치 | `flask` (하나만) → 신규 설치 필요. cv2는 **불필요**(이미지 처리를 GStreamer HW로 수행) |

> 참고: ArduCam 참고 코드(`ArduCam_Module_test/`)는 동일 AR0234 센서지만 **BA10 raw Bayer** 출력이라
> SW/GPU demosaic(ISP) 및 **GPIO 트리거** 동기화를 사용했다. e-con 모듈은 UYVY 출력 + `frame_sync`
> HW 동기라, 해당 ISP/GPU/GPIO 코드는 **전부 제거**하고 새로 작성한다. 구조(Flask + 모듈 패키지)만 계승한다.

## 4. 실행 환경 전략 (Environment)

- **지금 (이 도구):** `python3 -m venv --system-site-packages .venv` 후 `pip install flask`.
  시스템 `numpy`·GStreamer·Python `gi` 바인딩은 `--system-site-packages`로 재사용
  (venv 안에서 `import gi` 가능). **신규 pip 설치는 flask 하나뿐, 호스트 apt 무변경** →
  기존 e-con 드라이버 세팅 등 취약한 호스트 환경을 건드리지 않는다.
- **나중 (ROS2 통합, 별도 plan):** ROS2 베이스 이미지 기반 **Docker**로 전환.
  카메라 드라이버는 커널 공간이라 재설치 불필요, `docker run --device /dev/video0..3`로 패스스루.

## 5. 핵심 기술 결정 (Key Technical Decisions)

1. **캡처 + 이미지 처리 백엔드 = GStreamer (Python `gi` + `appsink`)**
   - 이유: Jetson **HW 가속**(`nvvidconv` 변환/스케일, `nvjpegenc` JPEG 인코딩)으로 CPU/GPU 부담을
     최소화한다(실측 검증됨). 이미지 변환/인코딩을 파이프라인에서 처리하므로 **cv2가 불필요**하다.
   - 프레임 획득: `appsink`에서 `pull-sample`로 버퍼를 가져오고, 버퍼의 **PTS**를 타임스탬프로 사용.
   - 대표 파이프라인 (정확한 caps는 구현 시 실측 검증):
     - 프리뷰/캡처: `v4l2src device=/dev/videoN ! video/x-raw,format=UYVY,width=W,height=H ! nvvidconv ! nvjpegenc ! image/jpeg ! appsink name=sinkN max-buffers=1 drop=true`
     - 동기 캡처: **하나의 파이프라인**에 선택된 N개 `v4l2src` 브랜치를 각각 `appsink name=sinkN`로 두어
       **단일 공유 클럭**을 공유 → 카메라 간 PTS가 동일 기준으로 비교 가능.
2. **동기 타임스탬프 = appsink 버퍼 PTS**
   - `v4l2src`는 커널 캡처 타임스탬프에서 PTS를 산출한다. 동기 캡처는 단일 파이프라인(공유 클럭)에서
     각 `appsink` 버퍼의 PTS를 읽어 카메라 간 편차/표준편차를 계산한다.
3. **동기화 설정 = 선택 카메라 전체에 `frame_sync=1`(30Hz)** (`v4l2-ctl -c frame_sync=1 -d /dev/videoN`).
   파이프라인 스트리밍 시작 전에 설정한다.
4. **카메라 컨트롤 get/set = `v4l2-ctl` subprocess 래퍼** (공식 가이드와 동일한 방식, 검증 용이).
5. **웹 = Flask** + 분리된 `templates/` · `static/` (참고 코드의 2105줄 단일 embedded HTML 지양).

## 6. 파일 구조 (File Structure)

```
econ_cam/
  __init__.py          # 패키지 공개 API 재노출
  gst_pipeline.py      # GStreamer 파이프라인 문자열 빌더(프리뷰/캡처/동기) — 순수 함수, 테스트 가능
  capture.py           # gi로 파이프라인 실행 + appsink pull → (jpeg, pts). Camera(단일/프리뷰), sync_capture(다중)
  controls.py          # v4l2-ctl 래퍼: 카메라 감지, 컨트롤 get/set, 해상도 목록, frame_sync 설정
  stats.py             # 타임스탬프 통계(min/max/최대편차/표준편차) 순수 계산 함수
  app.py               # Flask 서버 + API 라우트 (base64 헬퍼 포함)
  templates/
    index.html         # SPA (모드 3개 탭)
  static/
    app.js             # 프론트엔드 로직 (fetch, 미리보기, 모드 전환)
    style.css
run.py                 # 진입점: python3 run.py [--host --port --width --height]
tests/
  test_stats.py        # 타임스탬프 통계 계산 단위 테스트
  test_gst_pipeline.py # 파이프라인 문자열 빌더 단위 테스트
  test_controls.py     # v4l2-ctl 출력 파싱 단위 테스트 (샘플 텍스트)
requirements.txt       # flask (numpy·gi·GStreamer는 시스템)
captures/              # 저장 이미지 (.gitignore)
```

**설계 원칙**: 각 파일은 하나의 책임만 갖는다. 하드웨어/GStreamer에 의존하는 부분(`capture`,
`controls`의 subprocess 호출)과 순수 로직(`stats`, `gst_pipeline` 문자열 빌더, 파싱)을 분리하여
후자를 하드웨어 없이 단위 테스트할 수 있게 한다.

## 7. 모듈별 인터페이스 (Component Interfaces)

### `stats.py`
```python
def timestamp_stats(timestamps: dict[int, float]) -> dict:
    """{dev: ts_seconds} → {"per_camera": {dev: rel_ms}, "spread_ms": float,
       "std_ms": float, "ref_dev": int}. rel_ms 는 최소 타임스탬프 기준 상대값(ms)."""
```

### `gst_pipeline.py` (순수 문자열 빌더 — 하드웨어 불필요, 테스트 가능)
```python
def preview_pipeline(dev: int, width: int, height: int, sink_name: str = "sink") -> str:
    """v4l2src ! UYVY caps ! nvvidconv ! nvjpegenc ! image/jpeg ! appsink 문자열."""
def sync_pipeline(devs: list[int], width: int, height: int) -> str:
    """N개 v4l2src 브랜치 각각 appsink name=sink{dev} — 단일 공유 클럭 파이프라인 문자열."""
```

### `controls.py`
```python
def detect_cameras() -> list[dict]:
    """[{"dev": int, "name": str, "label": str}, ...] — ar0234 카드만."""
def list_resolutions(dev: int) -> list[tuple[int, int]]: ...
def get_controls(dev: int) -> dict: ...        # {name: {"value","min","max","type",...}}
def set_control(dev: int, name: str, value) -> bool: ...
def set_frame_sync(dev: int, mode: int) -> bool: ...  # 0/1/2
```

### `capture.py` (GStreamer 실행 — `gi` 사용)
```python
class Camera:
    """단일 카메라 GStreamer 파이프라인 소유 (프리뷰 + 단일 캡처)."""
    def __init__(self, dev: int, width: int, height: int): ...
    def start(self) -> None: ...                  # 파이프라인 PLAYING
    def latest_jpeg(self) -> bytes | None: ...    # appsink 최신 JPEG 버퍼 (MJPEG 프리뷰용)
    def capture(self) -> tuple[bytes, float]:     # (jpeg_bytes, pts_seconds)
    def stop(self) -> None: ...

def sync_capture(devs: list[int], width: int, height: int, sync_mode: int = 1) -> dict:
    """전 카메라 frame_sync 설정(controls.set_frame_sync) → 단일 공유클럭 파이프라인 실행 →
    각 appsink에서 1프레임 pull(jpeg, pts) → 통계 계산.
    반환: {"images": {dev: jpeg_bytes}, "timestamps": {dev: pts},
           "stats": <stats.timestamp_stats>}"""
```

### `app.py` — API 라우트
| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | SPA(index.html) |
| GET | `/api/cameras` | 감지된 카메라 목록 |
| POST | `/api/cameras/refresh` | 재감지 |
| POST | `/api/capture` | `{mode:"single"|"multi", devices:[...]}` → 이미지(b64) + (multi면) 타임스탬프/통계 |
| GET | `/api/stream/<dev>/mjpeg` | MJPEG multipart 라이브 스트림 |
| POST | `/api/stream/start` / `/api/stream/stop` | 스트림 시작/정지 |
| POST | `/api/save` | 현재 캡처 이미지 저장 → `captures/<timestamp>/` |
| GET / POST | `/api/params` | 카메라 컨트롤(exposure/gain 등) get/set |
| GET | `/api/resolutions` | 지원 해상도 목록 |
| POST | `/api/resolution` | 해상도 변경 |
| POST | `/api/frame_sync` | `frame_sync` 모드 설정 |

## 8. 3가지 모드 동작 (UX)

### Mode 1 — 단일 촬영
1. 카메라 1대 선택 → **라이브 MJPEG 프리뷰**(조준·초점 확인용)
2. **Capture** 버튼 → 그 순간 정지 프레임을 크게 표시
3. **Save** 버튼 → `captures/<timestamp>/videoN.jpg` 저장
4. (선택) exposure/gain 등 파라미터 슬라이더 조정

### Mode 2 — 다중 동기 촬영
1. 여러 카메라 체크박스로 선택
2. **Sync Capture** 버튼 → 선택 전체에 `frame_sync=1` 적용 후 병렬 캡처
3. 캡처된 이미지들을 **나란히(grid)** 표시
4. 아래에 **동기 지표** 표시:
   - 카메라별 상대 타임스탬프(ms, 최소 기준)
   - **최대 편차(spread = max − min)**
   - **표준편차(std)**
5. **Save All** → `captures/<timestamp>/` 에 전체 저장 + `sync_report.json`(타임스탬프/통계)

### Mode 3 — 캘리브레이션 (스켈레톤)
- 탭/레이아웃과 버튼 자리만 구성. 본문에 "캘리브레이션 기능은 추후 업데이트 예정" placeholder.

## 9. 검증 기준 (Success Criteria)

### 자동 (pytest, 하드웨어 불필요)
- `test_stats.py`: 알려진 타임스탬프 집합 → 최대편차·표준편차·상대값이 기대값과 일치.
- `test_gst_pipeline.py`: 파이프라인 문자열 빌더가 올바른 device/caps/appsink 이름을 포함하는지 검증.
- `test_controls.py`: 샘플 `v4l2-ctl` 출력 문자열 → 파서가 카메라 목록/컨트롤/해상도를 정확히 추출.

### 수동 (실제 4대 하드웨어)
- Mode 1: 프리뷰가 뜨고 Capture/Save 동작.
- Mode 2: 4대 동기 캡처 시 타임스탬프 편차/표준편차가 표시됨. `frame_sync=1`(ON)일 때가
  `frame_sync=0`(OFF)일 때보다 편차가 유의미하게 작음을 확인(동기화 실효성 검증).

## 10. 열린 항목 / 향후 (Out of scope, tracked)
- ROS2 노드/토픽 발행 (별도 spec/plan).
- 캘리브레이션 실제 연산 (Mode 3 확장) — 이 단계에서 `cv2`가 필요해지면 그때 추가.
- H.264 동영상 녹화(`nvv4l2h264enc`) — 현재는 정지 이미지 캡처에 집중, 필요 시 후속.
