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
