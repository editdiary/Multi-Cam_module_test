"""GStreamer 파이프라인 문자열 빌더 (순수 함수).

실기 검증된 파이프라인:
  v4l2src ! video/x-raw,format=UYVY ! nvvidconv ! nvjpegenc ! image/jpeg ! appsink
"""

# 프리뷰(스트리밍) 전용 다운스케일 해상도. 원본 촬영과 무관.
PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 360


def _branch(dev, width, height, sink_name):
    return (
        f"v4l2src device=/dev/video{dev} "
        f"! video/x-raw,format=UYVY,width={width},height={height} "
        f"! nvvidconv ! nvjpegenc ! image/jpeg "
        f"! appsink name={sink_name} max-buffers=1 drop=true sync=false"
    )


def preview_pipeline(
    dev,
    width,
    height,
    preview_width=PREVIEW_WIDTH,
    preview_height=PREVIEW_HEIGHT,
):
    """단일 카메라 프리뷰 + 원본 캡처 파이프라인.

    하나의 원본 소스를 tee로 분기한다:
    - preview 갈래: nvvidconv로 저해상도 다운스케일 → 상시 스트리밍(웹 부담 최소).
    - capture 갈래: valve(capgate, 평소 drop=true)로 게이트 → 촬영 순간에만 밸브를
      열어 원본 해상도 1프레임을 인코딩. 평소엔 원본 인코딩 부하 0.

    appsink 이름: preview / capture, valve 이름: capgate.
    """
    return (
        f"v4l2src device=/dev/video{dev} "
        f"! video/x-raw,format=UYVY,width={width},height={height} "
        f"! tee name=t "
        f"t. ! queue "
        f"! nvvidconv ! video/x-raw(memory:NVMM),width={preview_width},height={preview_height} "
        f"! nvjpegenc ! image/jpeg "
        f"! appsink name=preview max-buffers=1 drop=true sync=false "
        f"t. ! queue "
        f"! valve name=capgate drop=true "
        f"! nvvidconv ! nvjpegenc ! image/jpeg "
        # async=false: 밸브가 닫혀 이 appsink가 preroll을 못 해도 파이프라인
        # 전체가 PLAYING으로 전환되도록(프리뷰 갈래가 멈추지 않게) 한다.
        f"! appsink name=capture max-buffers=1 drop=true sync=false async=false"
    )


def sync_pipeline(devs, width, height):
    """다중 카메라 동기 캡처 — 단일 파이프라인에 카메라별 브랜치(공유 클럭).

    각 브랜치의 appsink 이름은 sink{dev}.
    """
    return "   ".join(_branch(d, width, height, f"sink{d}") for d in devs)
