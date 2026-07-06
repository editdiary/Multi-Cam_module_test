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


def match_frames(frames_by_dev):
    """카메라별 (pts, payload) 후보 중 PTS 편차가 최소인 세트를 고른다.

    Args:
        frames_by_dev: {dev: [(pts_seconds, payload), ...]}
    Returns:
        {dev: (pts, payload)}  — 편차 최소 세트(동점이면 더 최근 것).
        한 대라도 후보가 없으면 {}.
    """
    if not frames_by_dev or any(not v for v in frames_by_dev.values()):
        return {}
    anchors = sorted(pts for frames in frames_by_dev.values() for pts, _ in frames)
    best = None  # (key, chosen)
    for anchor in anchors:
        chosen = {
            dev: min(frames, key=lambda f: abs(f[0] - anchor))
            for dev, frames in frames_by_dev.items()
        }
        pts_vals = [f[0] for f in chosen.values()]
        # 편차 최소, (μs 이내로) 동점이면 더 최근 세트. spread를 양자화해 부동소수 오차로
        # recency tiebreak가 무력화되는 것을 막는다.
        key = (round(max(pts_vals) - min(pts_vals), 6), -anchor)
        if best is None or key < best[0]:
            best = (key, chosen)
    return best[1]
