import math

from econ_cam.stats import timestamp_stats


def test_empty():
    r = timestamp_stats({})
    assert r == {"per_camera": {}, "spread_ms": 0.0, "std_ms": 0.0, "ref_dev": None}


def test_single_camera():
    r = timestamp_stats({2: 10.5})
    assert r["per_camera"] == {2: 0.0}
    assert r["spread_ms"] == 0.0
    assert r["std_ms"] == 0.0
    assert r["ref_dev"] == 2


def test_multi_camera_relative_and_spread():
    # 초 단위 입력, ms 단위 상대값 출력
    r = timestamp_stats({0: 10.000, 1: 10.002, 2: 10.001})
    assert r["ref_dev"] == 0
    assert r["per_camera"][0] == 0.0
    assert math.isclose(r["per_camera"][1], 2.0, abs_tol=1e-6)
    assert math.isclose(r["per_camera"][2], 1.0, abs_tol=1e-6)
    assert math.isclose(r["spread_ms"], 2.0, abs_tol=1e-6)
    # 모집단 표준편차 pstdev([0,2,1]) = sqrt(2/3)
    assert math.isclose(r["std_ms"], math.sqrt(2 / 3), abs_tol=1e-6)
