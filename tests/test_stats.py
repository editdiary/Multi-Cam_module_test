import math

from econ_cam.stats import match_frames, timestamp_stats


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


def test_match_frames_picks_aligned_and_recent_set():
    chosen = match_frames({
        0: [(10.000, "a0"), (10.033, "b0")],
        1: [(10.001, "a1"), (10.034, "b1")],
    })
    assert chosen[0][1] == "b0"  # 편차 최소 + 더 최근 세트
    assert chosen[1][1] == "b1"
    pts = [chosen[0][0], chosen[1][0]]
    assert math.isclose(max(pts) - min(pts), 0.001, abs_tol=1e-6)


def test_match_frames_rejects_off_by_one():
    chosen = match_frames({
        0: [(10.033, "x0")],
        1: [(10.000, "y1"), (10.033, "z1")],  # off-by-one 후보 y1 존재
    })
    assert chosen[1][1] == "z1"  # x0 과 같은 시점의 z1 선택
    pts = [chosen[0][0], chosen[1][0]]
    assert math.isclose(max(pts) - min(pts), 0.0, abs_tol=1e-9)


def test_match_frames_empty_when_missing():
    assert match_frames({0: [(10.0, "p")], 1: []}) == {}
    assert match_frames({}) == {}
