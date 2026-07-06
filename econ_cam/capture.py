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
        sink = self._sink
        if sink is None:
            return None
        result = _pull(sink, 2.0)
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
