from econ_cam.calib_quality import verdict_from_metrics, coverage_state, diversity_check

GOOD = {"board_type": "checkerboard", "detected": True, "corner_ratio": 1.0,
        "sharpness": 300.0, "roi_mean": 130.0, "contrast": 200.0,
        "min_edge_frac": 0.10, "area_frac": 0.20}


def test_verdict_pass():
    v = verdict_from_metrics(GOOD)
    assert v["ok"] is True and v["reasons"] == []


def test_verdict_not_detected():
    v = verdict_from_metrics({**GOOD, "detected": False, "corner_ratio": 0.0})
    assert v["ok"] is False and any("찾지" in r for r in v["reasons"])


def test_verdict_blur_and_edge_fail():
    v = verdict_from_metrics({**GOOD, "sharpness": 20.0, "min_edge_frac": 0.001})
    assert v["ok"] is False
    assert v["checks"]["sharpness"] is False and v["checks"]["position"] is False


def test_verdict_exposure_fail():
    assert verdict_from_metrics({**GOOD, "roi_mean": 245.0})["checks"]["exposure"] is False
    assert verdict_from_metrics({**GOOD, "contrast": 10.0})["checks"]["exposure"] is False


def test_charuco_partial_corners_ok_but_checkerboard_not():
    partial = {**GOOD, "corner_ratio": 0.6}
    assert verdict_from_metrics({**partial, "board_type": "checkerboard"})["checks"]["corners"] is False
    assert verdict_from_metrics({**partial, "board_type": "charuco"})["checks"]["corners"] is True


def test_coverage_and_diversity():
    d_center = {"center_x": 0.5, "center_y": 0.5, "area_frac": 0.10}
    cov = coverage_state([d_center])
    assert cov["filled"] == 1 and cov["total"] == 27 and len(cov["suggestions"]) > 0
    # same cell -> not novel; far corner + different distance -> novel
    assert diversity_check(d_center, [d_center])["novel"] is False
    assert diversity_check({"center_x": 0.05, "center_y": 0.05, "area_frac": 0.02},
                           [d_center])["novel"] is True
