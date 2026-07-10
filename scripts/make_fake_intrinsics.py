#!/usr/bin/env python3
"""파이프라인 검증용 '가짜' intrinsic 세션 폴더 생성기. 실제 계산이 아니라 형식이 맞는 더미
K/왜곡을 만들어, Mode 4 '보정 확인'을 실제 캘리브레이션 없이 시험할 수 있게 한다.

사용: python3 scripts/make_fake_intrinsics.py [--session fake_data] [--devs 0 1 2 3]
      [--model pinhole|fisheye] [--width 1920 --height 1080]

결과: captures/calib/intrinsic/<session>/ 아래에
  - board_config.json
  - video<dev>/frame_000..003.jpg  (드롭다운 후보 판정용 더미 4장 — 실제 디코드는 안 됨)
  - video<dev>_<model>.json        (미리 놓는 가짜 intrinsic → '불러오기' 경로로 즉시 동작)

주의: 더미 jpg는 실제 이미지가 아니므로 '재계산'(force)은 실패한다. 이 스크립트는 어디까지나
      '로드 경로'(저장된 intrinsic으로 보정 스트림이 뜨는지) 검증용이다."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from econ_cam.calib_intrinsics import Intrinsics, save_intrinsics

BOARD = {"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25.0,
         "marker_mm": 0.0, "dictionary": "DICT_5X5_100"}


def fake_intrinsics(dev, model, width, height):
    fx = fy = width * 0.55
    cx, cy = width / 2.0, height / 2.0
    K = [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]]
    dist = [-0.05, 0.01, 0.0, 0.0] if model == "fisheye" else [-0.30, 0.10, 0.0, 0.0, 0.0]
    base = 0.45 + 0.05 * dev                     # 카메라마다 품질을 살짝 다르게
    offs = (0.02, -0.03, 0.10, 0.28, -0.05, 0.06, 0.15, 0.40, -0.01, 0.08, 0.19, 0.03)
    per_view = [round(max(0.05, base + d), 3) for d in offs]
    rms = round((sum(e * e for e in per_view) / len(per_view)) ** 0.5, 4)
    return Intrinsics(model=model, K=K, dist=dist, image_size=(width, height),
                      rms=rms, per_view_errors=per_view, n_images=len(per_view),
                      board=dict(BOARD))


def make_fake_session(root, session, devs, model, width, height):
    base = os.path.join(root, "captures", "calib", "intrinsic", session)
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "board_config.json"), "w") as f:
        json.dump(BOARD, f, indent=2)
    for dev in devs:
        vd = os.path.join(base, f"video{dev}")
        os.makedirs(vd, exist_ok=True)
        for i in range(4):                       # ≥4장이라야 드롭다운 후보(이미지 개수 판정)
            with open(os.path.join(vd, f"frame_{i:03d}.jpg"), "wb") as f:
                f.write(b"\xff\xd8\xff\xd9")     # 더미(빈) jpg
        intr = fake_intrinsics(dev, model, width, height)
        save_intrinsics(os.path.join(base, f"video{dev}_{model}.json"), intr)
        print(f"  video{dev}_{model}.json  (rms={intr.rms})")
    print(f"생성: {base}  (cam {devs}, model={model})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="fake_data")
    ap.add_argument("--devs", type=int, nargs="+", default=[0, 1, 2, 3])
    ap.add_argument("--model", default="pinhole", choices=["pinhole", "fisheye"])
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    a = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    make_fake_session(root, a.session, a.devs, a.model, a.width, a.height)


if __name__ == "__main__":
    main()
