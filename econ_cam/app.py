"""Flask 웹 서버 + API 라우트."""

import base64
import json
import os
import threading
import time
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from econ_cam import capture, controls

CAPTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "captures")


def jpeg_to_data_uri(jpeg_bytes):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def _json_stats(stats):
    """통계 dict를 JSON 직렬화 가능하게(키를 str로) 변환."""
    return {
        "per_camera": {str(k): round(v, 4) for k, v in stats["per_camera"].items()},
        "spread_ms": round(stats["spread_ms"], 4),
        "std_ms": round(stats["std_ms"], 4),
        "ref_dev": stats["ref_dev"],
    }


def create_app(width=1920, height=1080):
    app = Flask(__name__)
    state = {
        "cameras": [],
        "streams": {},     # {dev: capture.Camera} 단일 프리뷰 파이프라인
        "sync_session": None,  # capture.SyncSession 다중 공유클럭 파이프라인
        "last": {},        # {dev: jpeg_bytes} 최근 캡처
        "last_stats": None,
        "width": width,
        "height": height,
        "lock": threading.Lock(),
    }

    def stop_streams():
        for cam in state["streams"].values():
            cam.stop()
        state["streams"].clear()

    def stop_sync():
        if state["sync_session"] is not None:
            state["sync_session"].stop()
            state["sync_session"] = None

    def get_or_start_stream(dev):
        cam = state["streams"].get(dev)
        if cam is None:
            cam = capture.Camera(dev, state["width"], state["height"])
            cam.start()
            state["streams"][dev] = cam
        return cam

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/cameras")
    def api_cameras():
        if not state["cameras"]:
            state["cameras"] = controls.detect_cameras()
        return jsonify(state["cameras"])

    @app.route("/api/cameras/refresh", methods=["POST"])
    def api_cameras_refresh():
        with state["lock"]:
            stop_streams()
            stop_sync()
            state["cameras"] = controls.detect_cameras()
        return jsonify(state["cameras"])

    @app.route("/api/stream/<int:dev>/mjpeg")
    def api_stream(dev):
        with state["lock"]:
            cam = get_or_start_stream(dev)

        def gen():
            while True:
                jpeg = cam.latest_jpeg()
                if jpeg is None:
                    break
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                time.sleep(1 / 15)   # ~15fps — 조준용으로 충분, CPU 부하 완화

        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/api/stream/stop", methods=["POST"])
    def api_stream_stop():
        with state["lock"]:
            stop_streams()
        return jsonify({"ok": True})

    @app.route("/api/sync/start", methods=["POST"])
    def api_sync_start():
        data = request.get_json(force=True)
        devs = [int(d) for d in data["devices"]]
        sync_mode = int(data.get("sync_mode", 1))
        with state["lock"]:
            stop_streams()          # 단일 프리뷰가 device 점유 시 충돌 방지
            stop_sync()
            sess = capture.SyncSession(devs, state["width"], state["height"], sync_mode)
            sess.start()
            state["sync_session"] = sess
        return jsonify({"ok": True, "devices": devs})

    @app.route("/api/sync/stop", methods=["POST"])
    def api_sync_stop():
        with state["lock"]:
            stop_sync()
        return jsonify({"ok": True})

    @app.route("/api/sync/stream/<int:dev>")
    def api_sync_stream(dev):
        sess = state["sync_session"]
        if sess is None:
            return ("", 404)

        def gen():
            last = None
            while state["sync_session"] is sess:
                jpeg = sess.latest_jpeg(dev)
                if jpeg is not None and jpeg is not last:
                    last = jpeg
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                time.sleep(0.02)

        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/api/sync/status")
    def api_sync_status():
        sess = state["sync_session"]
        if sess is None:
            return jsonify({"active": False})
        st = sess.live_stats()
        if st is None:
            return jsonify({"active": True, "ready": False})
        return jsonify({"active": True, "ready": True, **_json_stats(st)})

    @app.route("/api/sync/capture", methods=["POST"])
    def api_sync_capture():
        with state["lock"]:
            sess = state["sync_session"]
            if sess is None:
                return jsonify({"ok": False, "error": "no session"}), 400
            result = sess.capture()
            state["last"] = result["images"]
            state["last_stats"] = result["stats"]
        images = {str(d): jpeg_to_data_uri(j) for d, j in result["images"].items()}
        return jsonify({"ok": True, "images": images, "stats": _json_stats(result["stats"])})

    @app.route("/api/shutdown", methods=["POST"])
    def api_shutdown():
        # 카메라 파이프라인을 먼저 정리해 /dev/videoN 을 깨끗이 해제한다.
        with state["lock"]:
            stop_streams()
            stop_sync()

        # HTTP 응답이 먼저 나간 뒤 프로세스를 종료한다.
        # Werkzeug 3.x 에는 server.shutdown 콜러블이 없어 os._exit 를 쓴다.
        # (atexit/DB/버퍼가 없으므로 즉시 종료해도 안전)
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return jsonify({"status": "shutting down"})

    @app.route("/api/capture", methods=["POST"])
    def api_capture():
        # 단일 촬영 전용. 다중 동기 촬영은 /api/sync/capture 로 이관.
        data = request.get_json(force=True)
        with state["lock"]:
            dev = int(data["devices"][0])
            cam = get_or_start_stream(dev)
            jpeg, _ = cam.capture()
            state["last"] = {dev: jpeg}
            state["last_stats"] = None
            return jsonify({"images": {str(dev): jpeg_to_data_uri(jpeg)}})

    @app.route("/api/save", methods=["POST"])
    def api_save():
        if not state["last"]:
            return jsonify({"ok": False, "error": "no capture"}), 400
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        outdir = os.path.join(CAPTURE_DIR, ts)
        os.makedirs(outdir, exist_ok=True)
        for dev, jpeg in state["last"].items():
            with open(os.path.join(outdir, f"video{dev}.jpg"), "wb") as f:
                f.write(jpeg)
        if state["last_stats"] is not None:
            with open(os.path.join(outdir, "sync_report.json"), "w") as f:
                json.dump(_json_stats(state["last_stats"]), f, indent=2)
        return jsonify({"ok": True, "path": outdir})

    @app.route("/api/resolutions")
    def api_resolutions():
        dev = int(request.args["dev"])
        return jsonify(controls.list_resolutions(dev))

    @app.route("/api/resolution", methods=["GET", "POST"])
    def api_resolution():
        if request.method == "GET":
            return jsonify({"width": state["width"], "height": state["height"]})
        data = request.get_json(force=True)
        with state["lock"]:
            state["width"] = int(data["width"])
            state["height"] = int(data["height"])
            stop_streams()
            stop_sync()
        return jsonify({"ok": True, "width": state["width"], "height": state["height"]})

    @app.route("/api/params")
    def api_get_params():
        dev = int(request.args["dev"])
        return jsonify(controls.get_controls(dev))

    @app.route("/api/params", methods=["POST"])
    def api_set_params():
        data = request.get_json(force=True)
        ok = controls.set_control(int(data["dev"]), data["name"], data["value"])
        return jsonify({"ok": ok})

    @app.route("/api/frame_sync", methods=["POST"])
    def api_frame_sync():
        data = request.get_json(force=True)
        mode = int(data["mode"])
        results = {int(d): controls.set_frame_sync(int(d), mode) for d in data["devices"]}
        return jsonify({"ok": all(results.values())})

    return app
