#!/usr/bin/env python3
"""e-con Multi-Cam 테스트 웹 서버 진입점.

사용법:
  python3 run.py
  python3 run.py --port 8888 --width 1920 --height 1080
"""

import argparse

from econ_cam.app import create_app


def main():
    parser = argparse.ArgumentParser(description="e-con Multi-Cam Test 웹 서버")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()

    app = create_app(args.width, args.height)
    # MJPEG 스트리밍과 동시 요청 처리를 위해 threaded=True
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
