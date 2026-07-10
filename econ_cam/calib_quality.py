"""Pure decision logic for calibration image validation & pose-diversity coverage.
Plain numbers/dicts only — no cv2/numpy (testable without hardware)."""

THRESH = {
    "min_sharpness": 100.0,   # variance-of-Laplacian floor (blur gate)
    "bright_lo": 40.0,        # board-ROI mean brightness floor (0-255)
    "bright_hi": 220.0,       # ceiling
    "min_contrast": 40.0,     # board-ROI (p95 - p5) floor; catches washed-out/glare/too-dark
    "edge_margin_frac": 0.02, # nearest corner must be >=2% of min(w,h) from every edge
    "min_area_frac": 0.03,    # board convex hull must fill >=3% of frame
    "charuco_min_ratio": 0.5, # charuco: >=50% of inner corners detected
}

COVER_GRID = 3                 # 3x3 spatial regions
DIST_BINS = (0.06, 0.15)       # area_frac splits -> far / mid / near
_REGION_NAME = {(0, 0): "좌상단", (1, 0): "상단", (2, 0): "우상단",
                (0, 1): "좌측", (1, 1): "중앙", (2, 1): "우측",
                (0, 2): "좌하단", (1, 2): "하단", (2, 2): "우하단"}
_DIST_NAME = {0: "원거리", 1: "중거리", 2: "근거리"}


def verdict_from_metrics(m: dict, t: dict = THRESH) -> dict:
    checks, reasons = {}, []

    def check(name, cond, msg):
        checks[name] = bool(cond)
        if not cond:
            reasons.append(msg)

    check("detected", m["detected"], "체커보드를 찾지 못했습니다")
    if m["detected"]:
        if m["board_type"] == "checkerboard":
            check("corners", m["corner_ratio"] >= 0.999, "교차점이 일부만 검출되었습니다")
        else:
            check("corners", m["corner_ratio"] >= t["charuco_min_ratio"],
                  "교차점이 너무 적게 검출되었습니다")
        check("sharpness", m["sharpness"] >= t["min_sharpness"], "이미지가 흐립니다 (초점/흔들림)")
        check("exposure",
              t["bright_lo"] <= m["roi_mean"] <= t["bright_hi"] and m["contrast"] >= t["min_contrast"],
              "명암이 부적절합니다 (과노출/과소노출/저대비)")
        check("position", m["min_edge_frac"] >= t["edge_margin_frac"],
              "보드가 화면 가장자리에 잘렸습니다")
        check("size", m["area_frac"] >= t["min_area_frac"], "보드가 너무 작습니다 (더 가까이)")
    ok = all(checks.values())
    return {"ok": ok, "reasons": reasons, "checks": checks}


def intrinsic_verdict(rms: float) -> dict:
    """재투영 오차(RMS, px)를 품질 등급으로. <0.5 매우좋음 / <1 양호 / <2 보통 / 그외 미흡."""
    if rms < 0.5:
        level, label = "excellent", "매우 좋음"
    elif rms < 1.0:
        level, label = "good", "양호"
    elif rms < 2.0:
        level, label = "fair", "보통"
    else:
        level, label = "poor", "미흡"
    return {"level": level, "label": label, "rms": round(float(rms), 4)}


def _cell(desc: dict):
    cx = min(COVER_GRID - 1, int(desc["center_x"] * COVER_GRID))
    cy = min(COVER_GRID - 1, int(desc["center_y"] * COVER_GRID))
    a = desc["area_frac"]
    d = 0 if a < DIST_BINS[0] else (1 if a < DIST_BINS[1] else 2)
    return (cx, cy, d)


def coverage_state(descs: list) -> dict:
    cells = {}
    for de in descs:
        k = "%d,%d,%d" % _cell(de)
        cells[k] = cells.get(k, 0) + 1
    total = COVER_GRID * COVER_GRID * 3   # 3 distance bins -> 27 cells
    suggestions = []
    for d in range(3):
        for cy in range(COVER_GRID):
            for cx in range(COVER_GRID):
                if "%d,%d,%d" % (cx, cy, d) not in cells:
                    suggestions.append(f"{_REGION_NAME[(cx, cy)]}·{_DIST_NAME[d]}")
    return {"cells": cells, "filled": len(cells), "total": total, "suggestions": suggestions[:5]}


def diversity_check(new_desc: dict, descs: list) -> dict:
    k = _cell(new_desc)
    same = sum(1 for de in descs if _cell(de) == k)
    if same == 0:
        return {"novel": True, "suggestion": ""}
    cx, cy, d = k
    return {"novel": False,
            "suggestion": f"{_REGION_NAME[(cx, cy)]}·{_DIST_NAME[d]} 구도는 이미 있습니다. "
                          f"다른 위치/거리에서 촬영을 권장합니다."}
