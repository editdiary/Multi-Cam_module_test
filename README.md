# Multi-Cam Module Test

e-con systems **AR0234 4-camera 모듈**을 위한 웹 기반 카메라 테스트 도구.
브라우저에서 카메라를 선택해 **단일 촬영 / 다중 동기 촬영 / 캘리브레이션**을 테스트하고,
하드웨어 `frame_sync` 기반 다중 카메라 동기화가 제대로 되는지 **정량적으로 검증**한다.

> **현재 상태:** 설계 확정 완료(spec), 구현 착수 예정.
> 상세 설계는 [`docs/superpowers/specs/2026-07-06-econ-multicam-test-design.md`](docs/superpowers/specs/2026-07-06-econ-multicam-test-design.md) 참조.

---

## 1. 목표

- 실행하면 연결된 카메라를 **자동 감지**하고, 웹에서 자유롭게 선택·테스트.
- 3가지 모드:
  1. **단일 카메라 촬영** — 라이브 프리뷰 → Capture → (Save)
  2. **다중 카메라 동기 촬영** — 여러 대 동시 촬영 + 동기화 품질(타임스탬프 편차/표준편차) 검증
  3. **캘리브레이션** — 레이아웃/기능 스켈레톤 (세부 기능은 추후 업데이트)
- (향후) 촬영 프로세스/이미지를 **ROS2 패키지**로 통합 — 별도 계획으로 분리.

## 2. 하드웨어 & 환경

| 항목 | 내용 |
|------|------|
| 플랫폼 | NVIDIA Jetson, JetPack 6.1 |
| 카메라 | e-con AR0234 **4대**, `/dev/video0` ~ `/dev/video3` (`tegra-video` CSI 드라이버) |
| 출력 포맷 | **UYVY** 4:2:2 (모듈에서 디베이어링 완료 — SW demosaic 불필요) |
| 해상도/FPS | `1280x720@120`, `1920x1080@65`, `1920x1200@60` |
| 동기화 | V4L2 `frame_sync` 컨트롤 (`0=Disable`, `1=30Hz`, `2=60Hz`) |

### 이미 설치되어 있는 것
- `numpy`, GStreamer 1.20.3 + Python 바인딩(`gi`, `GstApp`)
- HW 가속 플러그인: `nvvidconv`, `nvjpegenc`, `nvv4l2h264enc` (+ SW `jpegenc`)
- `v4l2-ctl`, `media-ctl`, `gst-launch-1.0`, Python 3.10

### 새로 필요한 것
- `flask` **하나만** (아래 설치 절차 참조). 이미지 처리를 GStreamer HW로 하므로 **cv2 불필요**.

## 3. 아키텍처

- **캡처 + 이미지 처리 = GStreamer** (Python `gi` + `appsink`).
  Jetson HW 가속(`nvvidconv` 변환, `nvjpegenc` JPEG)으로 CPU/GPU 부담 최소화.
- **동기 타임스탬프 = appsink 버퍼 PTS.**
  다중 동기 촬영은 **하나의 파이프라인에 N개 `v4l2src` 브랜치**를 두어 **단일 공유 클럭**을 공유 →
  카메라 간 PTS를 같은 기준으로 비교해 편차/표준편차를 계산.
- **동기화 = 선택 카메라 전체에 `frame_sync=1`(30Hz)** (`v4l2-ctl`로 설정, 스트리밍 시작 전).
- **웹 = Flask** + `templates/` · `static/` 분리.

### 디렉터리 구조 (구현 예정)
```
econ_cam/
  gst_pipeline.py    # GStreamer 파이프라인 문자열 빌더 (순수 함수)
  capture.py         # gi 파이프라인 실행 + appsink pull → (jpeg, pts). Camera / sync_capture
  controls.py        # v4l2-ctl 래퍼: 감지, 컨트롤 get/set, 해상도, frame_sync
  stats.py           # 타임스탬프 통계 (최대편차/표준편차)
  app.py             # Flask 서버 + API
  templates/index.html
  static/app.js, static/style.css
run.py               # 진입점
tests/               # pytest (순수 로직 단위 테스트)
captures/            # 저장 이미지 (.gitignore)
ArduCam_Module_test/ # 참고용 이전 구현 (구조만 참고, 코드는 재사용 안 함)
docs/superpowers/    # specs/ (설계), plans/ (구현 계획)
```

## 4. 설치

호스트 환경을 보호하기 위해 **가상환경(venv)** 을 사용한다. 시스템 패키지(numpy, GStreamer, `gi`)는
`--system-site-packages`로 재사용하고, pip로는 `flask`만 추가한다.

```bash
cd Multi-Cam_module_test
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install flask
```

> **ROS2 통합(향후):** ROS2는 venv/conda와 궁합이 좋지 않아 **Docker**로 전환 예정.
> 카메라 드라이버는 커널 공간이라 재설치가 필요 없고, `docker run --device /dev/video0..3`로 패스스루하면 된다.

## 5. 실행 & 사용

```bash
source .venv/bin/activate
python3 run.py                      # 기본 포트로 실행
python3 run.py --port 8888          # 포트 지정
```
브라우저에서 접속: `http://<jetson-ip>:8888/`

### Mode 1 — 단일 카메라 촬영
1. 카메라 1대 선택 → **라이브 프리뷰**(조준·초점 확인)
2. **Capture** → 정지 이미지 확인
3. **Save** → `captures/<timestamp>/videoN.jpg`
4. (선택) exposure/gain 등 파라미터 조정

### Mode 2 — 다중 카메라 동기 촬영
1. 여러 카메라 선택
2. **Sync Capture** → 선택 전체 `frame_sync=1` 적용 후 동기 촬영
3. 이미지들을 **나란히** 표시
4. **동기 지표** 표시: 카메라별 상대 타임스탬프 / **최대 편차(max−min)** / **표준편차**
5. **Save All** → `captures/<timestamp>/` + `sync_report.json`

> 육안 동기 검증은 별도의 **동기 검증용 영상**(움직이는 피사체)을 촬영해 나란히 비교하면 된다.

### Mode 3 — 캘리브레이션
- 레이아웃/버튼 스켈레톤만 제공. 세부 기능은 추후 업데이트.

## 6. 참고 명령어

```bash
# 동기 모드 설정 (공식 가이드)
v4l2-ctl -c frame_sync=1 -d /dev/video0

# 지원 포맷/해상도 확인
v4l2-ctl -d /dev/video0 --list-formats-ext

# 컨트롤 목록
v4l2-ctl -d /dev/video0 -L

# (참고) GStreamer 이미지 저장 — UYVY 캡처
gst-launch-1.0 v4l2src device=/dev/video0 num-buffers=1 \
  ! "video/x-raw, format=(string)UYVY, width=1920, height=1200" \
  ! jpegenc ! filesink location=out.jpg
```

## 7. 개발 / 테스트

순수 로직(타임스탬프 통계, 파이프라인 문자열 빌더, `v4l2-ctl` 출력 파싱)은 하드웨어 없이
`pytest`로 테스트한다. 실제 캡처·동기화는 4대 하드웨어에서 수동 검증한다.

```bash
source .venv/bin/activate
pip install pytest
pytest
```

## 8. 참고

- 이전 ArduCam 기반 구현: [`ArduCam_Module_test/`](ArduCam_Module_test/) — **구조만 참고**(BA10 Bayer +
  GPIO 트리거 기반이라 코드는 재사용하지 않음).
- 설계 문서: [`docs/superpowers/specs/2026-07-06-econ-multicam-test-design.md`](docs/superpowers/specs/2026-07-06-econ-multicam-test-design.md)
