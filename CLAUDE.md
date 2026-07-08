# CLAUDE.md

이 저장소에서 작업할 때 참고할 핵심 사항. 상세 설계는 아래 spec을 참조.

## 프로젝트
e-con AR0234 4-camera 모듈용 **웹 기반 카메라 테스트 도구** (Flask). 모드 3개: 단일 촬영 /
다중 동기 촬영(+동기 검증) / 캘리브레이션(체커보드·ChArUco 이미지 수집+검증; intrinsic/extrinsic).
ROS2 통합은 별도 계획으로 분리.

## 하드웨어 핵심 사실
- 카메라 4대: `/dev/video0`~`/dev/video3` (e-con AR0234, `tegra-video` CSI)
- 포맷: **UYVY** 4:2:2 (디베이어링 완료 → SW demosaic 불필요)
- 해상도: `1280x720@120`, `1920x1080@65`, `1920x1200@60`
- 동기화: V4L2 `frame_sync` (`0/1/2` = Disable/30Hz/60Hz), 설정: `v4l2-ctl -c frame_sync=1 -d /dev/videoN`

## 기술 결정 (확정)
- **캡처+이미지처리 = GStreamer** (Python `gi` + `appsink`, HW `nvvidconv`/`nvjpegenc`).
  촬영·인코딩에는 cv2 미사용. **단, Mode 3 캘리브레이션의 체커보드/ChArUco 코너 검출·품질 검증에는
  cv2 사용**(`opencv-contrib-python`, venv 전용). 실제 K/extrinsic 행렬 계산은 오프라인 후속(범위 밖).
- **동기 타임스탬프 = appsink 버퍼 PTS**. 다중 동기는 **단일 파이프라인(N개 v4l2src, 공유 클럭)** 에서 PTS 비교.
- **환경 = venv** (`--system-site-packages`) + `pip install -r requirements.txt`
  (flask + opencv-contrib-python). GStreamer·`gi`는 시스템 재사용. numpy는 opencv 4.8 요구로
  venv에 1.24.4 설치(시스템 numpy 1.21.5는 그대로 둠). 호스트 apt 무변경(취약한 드라이버 환경 보호).
  ROS2 단계에서 Docker로 전환.
- 컨트롤 get/set = `v4l2-ctl` subprocess 래퍼.

## 작업 규칙
- `ArduCam_Module_test/`는 **구조 참고 전용** — 코드 재사용 금지(BA10 Bayer/GPIO 기반이라 부적합).
- 순수 로직(stats, 파이프라인 문자열 빌더, 파싱, 캘리브레이션 보드/검증 로직)은 하드웨어 없이
  `pytest`로 검증. 실제 캡처·동기·캘리브레이션 촬영은 4대에서 수동 검증.
- 파일은 관심사별로 작게 유지: `econ_cam/{gst_pipeline,capture,controls,stats,app}.py`.
  캘리브레이션은 `econ_cam/{calib_board,calib_quality,calib_detect}.py`
  (board·quality는 순수 로직, detect는 cv2).

## Git 작업 방식
- **새 기능 추가·테스트는 항상 새 브랜치**에서 진행한다(`main`/`develop`에서 직접 작업 금지).
- **브랜치 병합·푸시는 사용자가 직접** 한다 — Claude는 하지 않는다:
  - 모든 기능이 의도대로 동작함을 확인한 경우에만 사용자가 `develop`으로 merge.
  - `develop`에서 정상 운용이 확인된 경우에만 사용자가 `main`으로 merge.
- 즉 Claude는 새 작업용 브랜치를 만들고 **커밋까지만** 수행하며, `develop`/`main`으로의 merge와
  원격 push는 사용자의 지시/직접 수행을 기다린다.

## 상세 문서 (필요 시 참조)
- 설계 스펙: @docs/superpowers/specs/2026-07-06-econ-multicam-test-design.md
- 구현 계획: `docs/superpowers/plans/` (`2026-07-06-econ-multicam-test.md`, `2026-07-08-calibration-mode.md`)
- 사용 설명서: `docs/USAGE.md`
