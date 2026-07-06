# CLAUDE.md

이 저장소에서 작업할 때 참고할 핵심 사항. 상세 설계는 아래 spec을 참조.

## 프로젝트
e-con AR0234 4-camera 모듈용 **웹 기반 카메라 테스트 도구** (Flask). 모드 3개: 단일 촬영 /
다중 동기 촬영(+동기 검증) / 캘리브레이션(스켈레톤). ROS2 통합은 별도 계획으로 분리.

## 하드웨어 핵심 사실
- 카메라 4대: `/dev/video0`~`/dev/video3` (e-con AR0234, `tegra-video` CSI)
- 포맷: **UYVY** 4:2:2 (디베이어링 완료 → SW demosaic 불필요)
- 해상도: `1280x720@120`, `1920x1080@65`, `1920x1200@60`
- 동기화: V4L2 `frame_sync` (`0/1/2` = Disable/30Hz/60Hz), 설정: `v4l2-ctl -c frame_sync=1 -d /dev/videoN`

## 기술 결정 (확정)
- **캡처+이미지처리 = GStreamer** (Python `gi` + `appsink`, HW `nvvidconv`/`nvjpegenc`). **cv2 사용 안 함.**
- **동기 타임스탬프 = appsink 버퍼 PTS**. 다중 동기는 **단일 파이프라인(N개 v4l2src, 공유 클럭)** 에서 PTS 비교.
- **환경 = venv** (`--system-site-packages`) + `pip install flask`. numpy·GStreamer·`gi`는 시스템 재사용.
  호스트 apt 무변경(취약한 드라이버 환경 보호). ROS2 단계에서 Docker로 전환.
- 컨트롤 get/set = `v4l2-ctl` subprocess 래퍼.

## 작업 규칙
- `ArduCam_Module_test/`는 **구조 참고 전용** — 코드 재사용 금지(BA10 Bayer/GPIO 기반이라 부적합).
- 순수 로직(stats, 파이프라인 문자열 빌더, 파싱)은 하드웨어 없이 `pytest`로 검증. 실제 캡처는 4대에서 수동 검증.
- 파일은 관심사별로 작게 유지: `econ_cam/{gst_pipeline,capture,controls,stats,app}.py`.

## 상세 문서 (필요 시 참조)
- 설계 스펙: @docs/superpowers/specs/2026-07-06-econ-multicam-test-design.md
- 구현 계획: `docs/superpowers/plans/` (작성 예정)
