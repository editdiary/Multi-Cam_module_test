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
