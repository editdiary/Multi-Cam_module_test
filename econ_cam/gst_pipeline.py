"""GStreamer 파이프라인 문자열 빌더 (순수 함수).

실기 검증된 파이프라인:
  v4l2src ! video/x-raw,format=UYVY ! nvvidconv ! nvjpegenc ! image/jpeg ! appsink
"""

# 프리뷰(스트리밍) 전용 다운스케일 해상도. 원본 촬영과 무관.
PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 360

CAPTURE_FRAMES = 4  # 촬영 시 카메라별로 모을 원본 프레임 수(PTS 매칭 후보)


def _tee_branch(dev, width, height, preview_width, preview_height,
                suffix="", capture_buffers=1):
    """v4l2src → tee → (저해상도 프리뷰 appsink) + (valve 게이트 원본 캡처 appsink).

    하나의 원본 소스를 tee로 분기한다:
    - preview 갈래: nvvidconv로 저해상도 다운스케일 → 상시 스트리밍(웹 부담 최소).
    - capture 갈래: valve(capgate, 평소 drop=true)로 게이트 → 촬영 순간에만 밸브를
      열어 원본 해상도 프레임을 인코딩. 평소엔 원본 인코딩 부하 0.

    appsink/valve 이름에 suffix를 붙여 한 파이프라인에 여러 브랜치를 공유 클럭으로 둘 수 있다.
    async=false: 밸브가 닫혀 capture appsink가 preroll을 못 해도 파이프라인 전체가
    PLAYING으로 전환되도록(프리뷰 갈래가 멈추지 않게) 한다.
    """
    return (
        f"v4l2src device=/dev/video{dev} "
        f"! video/x-raw,format=UYVY,width={width},height={height} "
        f"! tee name=t{suffix} "
        f"t{suffix}. ! queue "
        f"! nvvidconv ! video/x-raw(memory:NVMM),width={preview_width},height={preview_height} "
        f"! nvjpegenc ! image/jpeg "
        f"! appsink name=preview{suffix} max-buffers=1 drop=true sync=false "
        f"t{suffix}. ! queue "
        f"! valve name=capgate{suffix} drop=true "
        f"! nvvidconv ! nvjpegenc ! image/jpeg "
        f"! appsink name=capture{suffix} max-buffers={capture_buffers} drop=true sync=false async=false"
    )


def preview_pipeline(
    dev,
    width,
    height,
    preview_width=PREVIEW_WIDTH,
    preview_height=PREVIEW_HEIGHT,
):
    """단일 카메라 프리뷰 + 원본 캡처. appsink 이름: preview / capture, valve: capgate."""
    return _tee_branch(dev, width, height, preview_width, preview_height)


def sync_live_pipeline(
    devs,
    width,
    height,
    preview_width=PREVIEW_WIDTH,
    preview_height=PREVIEW_HEIGHT,
):
    """다중 카메라 라이브+동기 캡처 — 카메라별 브랜치(단일 공유 클럭).

    브랜치별 이름: preview{dev} / capture{dev} / capgate{dev}. 캡처 appsink는 PTS 매칭
    후보를 모으기 위해 max-buffers=CAPTURE_FRAMES.
    """
    return "   ".join(
        _tee_branch(d, width, height, preview_width, preview_height,
                    suffix=str(d), capture_buffers=CAPTURE_FRAMES)
        for d in devs
    )
