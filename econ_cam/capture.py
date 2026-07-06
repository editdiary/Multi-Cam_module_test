"""GStreamer 기반 카메라 캡처 (Python gi + appsink).

- Camera: 단일 카메라 파이프라인 (저해상도 프리뷰 + 원본 캡처, tee+valve)
- SyncSession: 단일 공유클럭 파이프라인으로 다중 카메라 라이브 프리뷰 + 동기 캡처

appsink 버퍼 PTS(ns)를 초 단위로 변환해 타임스탬프로 사용한다.
단일/다중 모두 하나의 원본 소스를 tee로 나눠 저해상도 프리뷰를 상시 송출하고,
원본 캡처 갈래는 valve로 게이트해 촬영 순간에만 원본 프레임을 인코딩한다.
다중 동기 캡처는 전 카메라 valve를 동시에 열어 카메라별로 원본 프레임을 여러 개 모은 뒤,
stats.match_frames 로 PTS가 가장 잘 맞는 동일 시점 세트를 선택한다. 이렇게 프레임 인덱스를
맞춰 골라야 pull 타이밍이 프레임 경계에 걸쳐 한 대만 한 프레임 어긋나는 현상을 막을 수 있다
(공유 클럭이라 카메라 간 PTS 비교가 유효).
"""

import threading
import time

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from econ_cam import controls, gst_pipeline, stats  # noqa: E402

Gst.init(None)

_PULL_TIMEOUT_S = 3.0
_RING = 5             # 라이브 status용 카메라별 최근 PTS 개수
_DRAIN_TIMEOUT_S = 0  # 즉시 pull(있으면 반환, 없으면 None)


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
    """단일 카메라 GStreamer 파이프라인 (저해상도 프리뷰 + 원본 캡처).

    프리뷰(preview appsink)는 상시 저해상도로 흐르고, 원본 캡처(capture appsink)는
    valve(capgate)로 게이트되어 capture() 호출 순간에만 밸브를 열어 원본 1프레임을
    받는다. 프리뷰는 캡처 중에도 끊기지 않는다.
    """

    def __init__(self, dev, width, height):
        self.dev = dev
        self.width = width
        self.height = height
        self._pipeline = None
        self._preview = None
        self._capture = None
        self._valve = None

    def start(self):
        desc = gst_pipeline.preview_pipeline(self.dev, self.width, self.height)
        self._pipeline = Gst.parse_launch(desc)
        self._preview = self._pipeline.get_by_name("preview")
        self._capture = self._pipeline.get_by_name("capture")
        self._valve = self._pipeline.get_by_name("capgate")
        self._pipeline.set_state(Gst.State.PLAYING)

    def latest_jpeg(self):
        sink = self._preview
        if sink is None:
            return None
        result = _pull(sink, 2.0)
        return result[0] if result else None

    def capture(self):
        sink = self._capture
        valve = self._valve
        if sink is None or valve is None:
            raise RuntimeError(f"camera /dev/video{self.dev} not started")
        # 밸브를 열기 전, 이전 캡처의 잔여 버퍼를 비워 최신 프레임만 얻는다.
        while _pull(sink, 0) is not None:
            pass
        valve.set_property("drop", False)
        try:
            result = _pull(sink, _PULL_TIMEOUT_S)
        finally:
            valve.set_property("drop", True)
        if result is None:
            raise RuntimeError(f"capture timeout on /dev/video{self.dev}")
        return result

    def stop(self):
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._preview = None
            self._capture = None
            self._valve = None


class SyncSession:
    """선택 카메라 전체를 하나의 공유 클럭 파이프라인으로 운용.

    - 프리뷰 appsink(new-sample 콜백)로 최신 JPEG + 최근 PTS 링을 유지 → 라이브 스트림/status.
    - capture(): 전 카메라 valve 동시 개방 → 짧은 창 동안 카메라별 원본 프레임을 여러 개 수집 →
      stats.match_frames 로 PTS가 가장 잘 맞는 동일 시점 세트 선택(off-by-one 프레임 제거).
    """

    def __init__(self, devs, width, height, sync_mode=1):
        self.devs = [int(d) for d in devs]
        self.width, self.height, self.sync_mode = width, height, sync_mode
        self._pipeline = None
        self._capture = {}       # {dev: capture appsink}
        self._valve = {}         # {dev: valve}
        self._latest = {}        # {dev: jpeg bytes}
        self._pts_ring = {}      # {dev: [pts, ...]}
        self._lock = threading.Lock()

    def start(self):
        for d in self.devs:
            controls.set_frame_sync(d, self.sync_mode)
        desc = gst_pipeline.sync_live_pipeline(self.devs, self.width, self.height)
        self._pipeline = Gst.parse_launch(desc)
        for d in self.devs:
            self._capture[d] = self._pipeline.get_by_name(f"capture{d}")
            self._valve[d] = self._pipeline.get_by_name(f"capgate{d}")
            preview = self._pipeline.get_by_name(f"preview{d}")
            preview.set_property("emit-signals", True)
            preview.connect("new-sample", self._on_preview, d)
        self._pipeline.set_state(Gst.State.PLAYING)

    def _on_preview(self, sink, dev):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        data = buf.extract_dup(0, buf.get_size())
        pts = buf.pts / 1e9
        with self._lock:
            self._latest[dev] = data
            ring = self._pts_ring.setdefault(dev, [])
            ring.append(pts)
            del ring[:-_RING]
        return Gst.FlowReturn.OK

    def latest_jpeg(self, dev):
        with self._lock:
            return self._latest.get(dev)

    def live_stats(self):
        with self._lock:
            rings = {d: [(p, None) for p in r] for d, r in self._pts_ring.items() if r}
        if len(rings) < len(self.devs):
            return None
        chosen = stats.match_frames(rings)
        if not chosen:
            return None
        return stats.timestamp_stats({d: c[0] for d, c in chosen.items()})

    def capture(self):
        # (CAPTURE_FRAMES+1)프레임 이상 쌓일 시간. 30Hz→~0.17s, 여유 포함.
        rate = 60.0 if self.sync_mode == 2 else 30.0
        window = (gst_pipeline.CAPTURE_FRAMES + 1) / rate
        with self._lock_valves():
            # 워밍업: 각 카메라의 첫 프레임을 블로킹으로 기다려 파이프라인이 실제로
            # 프레임을 낼 때까지 대기(센서 시작 지연 흡수). 이후 창만큼 쌓고 드레인하면
            # 카메라 간 후보 PTS 구간이 겹쳐 match_frames 가 동일 시점 세트를 찾는다.
            for d in self.devs:
                if _pull(self._capture[d], _PULL_TIMEOUT_S) is None:
                    raise RuntimeError(f"sync capture timeout on /dev/video{d}")
            time.sleep(window)
            frames = {d: self._drain(self._capture[d]) for d in self.devs}
        chosen = stats.match_frames(frames)
        if not chosen:
            raise RuntimeError("sync capture: no matching frames")
        images = {d: c[1] for d, c in chosen.items()}
        timestamps = {d: c[0] for d, c in chosen.items()}
        return {"images": images, "timestamps": timestamps,
                "stats": stats.timestamp_stats(timestamps)}

    def _lock_valves(self):
        """전 카메라 valve 동시 개방/폐쇄 컨텍스트. 열기 전 잔여 프레임을 비운다."""
        session = self

        class _Ctx:
            def __enter__(self):
                for d in session.devs:
                    session._drain(session._capture[d])
                    session._valve[d].set_property("drop", False)

            def __exit__(self, *a):
                for d in session.devs:
                    session._valve[d].set_property("drop", True)

        return _Ctx()

    def _drain(self, sink):
        """appsink에 쌓인 버퍼를 모두 꺼내 [(pts, jpeg), ...] 로 반환(없으면 [])."""
        out = []
        while True:
            r = _pull(sink, _DRAIN_TIMEOUT_S)
            if r is None:
                break
            jpeg, pts = r
            out.append((pts, jpeg))  # match_frames 는 (pts, payload)
        return out

    def stop(self):
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._capture.clear()
            self._valve.clear()
            self._latest.clear()
            self._pts_ring.clear()
