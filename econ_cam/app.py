"""Flask 웹 서버 + API 라우트."""

import base64
import json
import os
import threading
import time
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

from econ_cam import capture, controls, calib_board, calib_detect, calib_quality

CAPTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "captures")
CALIB_DIR = os.path.join(CAPTURE_DIR, "calib")


def jpeg_to_data_uri(jpeg_bytes):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def _round_metrics(m):
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}


def _calib_evaluate(jpeg, cfg):
    """detect → metrics → verdict → descriptor → overlay for one image."""
    gray, corners, n = calib_detect.detect_board(jpeg, cfg)
    metrics = calib_detect.quality_metrics(gray, corners, cfg)
    verdict = calib_quality.verdict_from_metrics(metrics)
    desc = calib_detect.pose_descriptor(gray, corners) if corners is not None else None
    overlay = calib_detect.overlay_corners(jpeg, cfg, corners)
    return {"jpeg": jpeg, "overlay": overlay, "metrics": metrics,
            "verdict": verdict, "desc": desc, "count": n}


def _calib_counts(cs):
    if cs["sub_mode"] == "intrinsic":
        dev = cs["devices"][0]
        return {str(dev): len(cs["descs"][dev])}
    return {"shots": len(cs["shots"])}


def _pairs_list(cs):
    return [{"pair": f"{a}-{b}", "count": c} for (a, b), c in cs["pair_counts"].items()]


def _write_calib_report(cs):
    report = {"board": cs["cfg"].to_dict(), "sub_mode": cs["sub_mode"]}
    if cs["sub_mode"] == "intrinsic":
        report["cameras"] = {str(d): cs["reports"][d] for d in cs["devices"]}
    else:
        report["shots"] = cs["shots"]
        report["pair_counts"] = {f"{a}-{b}": c for (a, b), c in cs["pair_counts"].items()}
    with open(os.path.join(cs["session_dir"], "report.json"), "w") as f:
        json.dump(report, f, indent=2)


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
        "calib": None,     # 캘리브레이션 세션 accumulator (아래 /api/calib/* 참조)
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
            # 콜드 스타트(센서 워밍업)에서 첫 프레임이 2초 pull timeout을 넘겨 None이 와도
            # 스트림을 끊지 않는다. 이 스트림이 해당 dev의 현재 카메라인 동안만 지속되며
            # (정지/교체 시 자동 종료), 프레임이 나오기 시작하면 재감지 없이 자동 복구된다.
            while state["streams"].get(dev) is cam:
                jpeg = cam.latest_jpeg()
                if jpeg is None:
                    continue
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

    # ---- 캘리브레이션 (Mode 3) ------------------------------------------------
    # 촬영+검증 전용. 실제 K/extrinsic 연산은 오프라인 후속 단계(범위 밖).
    # intrinsic: 단일 카메라(Camera + /api/stream). extrinsic: 다중 동기(SyncSession + /api/sync).

    @app.route("/api/calib/start", methods=["POST"])
    def api_calib_start():
        data = request.get_json(force=True)
        sub_mode = data.get("sub_mode")
        if sub_mode not in ("intrinsic", "extrinsic"):
            return jsonify({"ok": False, "error": "invalid sub_mode"}), 400
        try:
            cfg = calib_board.parse_board_config(data["board"])
        except (ValueError, KeyError) as e:
            return jsonify({"ok": False, "error": f"보드 설정 오류: {e}"}), 400
        devices = [int(d) for d in data.get("devices", [])]
        if not devices:
            return jsonify({"ok": False, "error": "카메라를 선택하세요"}), 400
        ring = bool(data.get("ring", False))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(CALIB_DIR, sub_mode, ts)
        os.makedirs(session_dir, exist_ok=True)
        with open(os.path.join(session_dir, "board_config.json"), "w") as f:
            json.dump(cfg.to_dict(), f, indent=2)
        pairs = calib_board.adjacent_pairs(devices, ring) if sub_mode == "extrinsic" else []
        with state["lock"]:
            state["calib"] = {
                "sub_mode": sub_mode, "cfg": cfg, "devices": devices, "ring": ring,
                "session_dir": session_dir,
                "descs": {d: [] for d in devices},
                "reports": {d: [] for d in devices},
                "pair_counts": {p: 0 for p in pairs},
                "shots": [],
                "pending": None,
            }
            cs = state["calib"]
        resp = {"ok": True, "sub_mode": sub_mode, "board": cfg.to_dict(),
                "session_dir": session_dir, "counts": _calib_counts(cs)}
        if sub_mode == "extrinsic":
            resp["pairs"] = _pairs_list(cs)
        return jsonify(resp)

    @app.route("/api/calib/capture", methods=["POST"])
    def api_calib_capture():
        cs = state["calib"]
        if cs is None:
            return jsonify({"ok": False, "error": "세션이 없습니다"}), 400
        cfg = cs["cfg"]
        if cs["sub_mode"] == "intrinsic":
            dev = cs["devices"][0]
            with state["lock"]:
                cam = get_or_start_stream(dev)
                jpeg, _ = cam.capture()
            ev = _calib_evaluate(jpeg, cfg)
            cs["pending"] = {dev: ev}
            div = (calib_quality.diversity_check(ev["desc"], cs["descs"][dev])
                   if ev["desc"] is not None else {"novel": True, "suggestion": ""})
            return jsonify({"ok": True, "verdict": ev["verdict"],
                            "metrics": _round_metrics(ev["metrics"]),
                            "overlay": {str(dev): jpeg_to_data_uri(ev["overlay"])},
                            "diversity": div})
        # extrinsic: 동기 세션에서 1세트 캡처 → 카메라별 검증 → 인접 쌍 동시검출 판정
        with state["lock"]:
            sess = state["sync_session"]
            if sess is None:
                return jsonify({"ok": False,
                                "error": "동기 세션이 없습니다 (카메라 선택 후 프리뷰를 시작하세요)"}), 400
            result = sess.capture()
        evs = {dev: _calib_evaluate(jpeg, cfg) for dev, jpeg in result["images"].items()}
        covered = [(a, b) for (a, b) in cs["pair_counts"].keys()
                   if a in evs and b in evs
                   and evs[a]["verdict"]["ok"] and evs[b]["verdict"]["ok"]]
        reasons = []
        for dev in cs["devices"]:
            ev = evs.get(dev)
            if ev is None:
                reasons.append(f"video{dev}: 캡처 없음")
            elif not ev["verdict"]["ok"]:
                reasons.append(f"video{dev}: " + ", ".join(ev["verdict"]["reasons"]))
        covered_str = [f"{a}-{b}" for (a, b) in covered]
        verdict = {"ok": len(covered) > 0,
                   "reasons": ([] if covered else ["동시에 선명히 검출된 인접 쌍이 없습니다"] + reasons),
                   "covered_pairs": covered_str,
                   "per_cam": {str(d): ev["verdict"] for d, ev in evs.items()}}
        cs["pending"] = {"evs": evs, "covered": covered, "sync_stats": result["stats"]}
        return jsonify({"ok": True, "verdict": verdict,
                        "metrics": {str(d): _round_metrics(ev["metrics"]) for d, ev in evs.items()},
                        "overlay": {str(d): jpeg_to_data_uri(ev["overlay"]) for d, ev in evs.items()},
                        "sync_stats": _json_stats(result["stats"]),
                        "covered_pairs": covered_str})

    @app.route("/api/calib/accept", methods=["POST"])
    def api_calib_accept():
        cs = state["calib"]
        if cs is None or not cs.get("pending"):
            return jsonify({"ok": False, "error": "저장할 캡처가 없습니다"}), 400
        pend = cs["pending"]
        if cs["sub_mode"] == "intrinsic":
            dev, ev = next(iter(pend.items()))
            if not ev["verdict"]["ok"]:
                return jsonify({"ok": False, "error": "검증 미통과 — 저장 불가"}), 400
            idx = len(cs["descs"][dev])
            devdir = os.path.join(cs["session_dir"], f"video{dev}")
            os.makedirs(devdir, exist_ok=True)
            fname = f"frame_{idx:03d}.jpg"
            with open(os.path.join(devdir, fname), "wb") as f:
                f.write(ev["jpeg"])
            cs["descs"][dev].append(ev["desc"])
            cs["reports"][dev].append({"file": f"video{dev}/{fname}",
                                       "metrics": _round_metrics(ev["metrics"]),
                                       "descriptor": ev["desc"]})
            _write_calib_report(cs)
            cs["pending"] = None
            return jsonify({"ok": True, "counts": _calib_counts(cs),
                            "coverage": calib_quality.coverage_state(cs["descs"][dev])})
        # extrinsic
        if not pend["covered"]:
            return jsonify({"ok": False, "error": "검증 미통과 — 저장 불가"}), 400
        idx = len(cs["shots"])
        shotdir = os.path.join(cs["session_dir"], f"shot_{idx:03d}")
        os.makedirs(shotdir, exist_ok=True)
        # 검증 통과(사용 가능)한 카메라의 이미지만 저장한다. 감지 실패/품질 미달 카메라는
        # 파일을 남기지 않고 detections.json 에 사유만 기록 → "어떤 이미지가 유효한지" 명확.
        det = {}
        saved = []
        for dev, ev in pend["evs"].items():
            usable = ev["verdict"]["ok"]
            entry = {"detected": ev["metrics"]["detected"],
                     "corner_count": ev["count"],
                     "usable": usable,
                     "metrics": _round_metrics(ev["metrics"])}
            if usable:
                with open(os.path.join(shotdir, f"video{dev}.jpg"), "wb") as f:
                    f.write(ev["jpeg"])
                entry["file"] = f"video{dev}.jpg"
                saved.append(dev)
            else:
                entry["reasons"] = ev["verdict"]["reasons"]
            det[str(dev)] = entry
        saved_files = [f"video{d}" for d in sorted(saved)]
        covered_str = [f"{a}-{b}" for (a, b) in pend["covered"]]
        sync_stats = _json_stats(pend["sync_stats"])
        with open(os.path.join(shotdir, "detections.json"), "w") as f:
            json.dump({"cameras": det, "saved_cameras": saved_files,
                       "covered_pairs": covered_str, "sync_stats": sync_stats}, f, indent=2)
        for p in pend["covered"]:
            cs["pair_counts"][p] += 1
        cs["shots"].append({"dir": f"shot_{idx:03d}", "saved_cameras": saved_files,
                            "covered_pairs": covered_str, "sync_stats": sync_stats})
        _write_calib_report(cs)
        cs["pending"] = None
        return jsonify({"ok": True, "counts": _calib_counts(cs), "pairs": _pairs_list(cs)})

    @app.route("/api/calib/status")
    def api_calib_status():
        cs = state["calib"]
        if cs is None:
            return jsonify({"active": False})
        resp = {"active": True, "sub_mode": cs["sub_mode"], "board": cs["cfg"].to_dict(),
                "counts": _calib_counts(cs), "session_dir": cs["session_dir"]}
        if cs["sub_mode"] == "intrinsic":
            dev = cs["devices"][0]
            resp["coverage"] = calib_quality.coverage_state(cs["descs"][dev])
        else:
            resp["pairs"] = _pairs_list(cs)
        return jsonify(resp)

    @app.route("/api/calib/reset", methods=["POST"])
    def api_calib_reset():
        with state["lock"]:
            state["calib"] = None
        return jsonify({"ok": True})

    @app.route("/api/calib/sessions")
    def api_calib_sessions():
        sub_mode = request.args.get("sub_mode", "intrinsic")
        base = os.path.join(CALIB_DIR, sub_mode)
        out = []
        if os.path.isdir(base):
            for name in sorted(os.listdir(base), reverse=True):
                bpath = os.path.join(base, name, "board_config.json")
                if not os.path.isfile(bpath):
                    continue
                rpath = os.path.join(base, name, "report.json")
                count = 0
                if os.path.isfile(rpath):
                    with open(rpath) as f:
                        rep = json.load(f)
                    if sub_mode == "intrinsic":
                        count = sum(len(v) for v in rep.get("cameras", {}).values())
                    else:
                        count = len(rep.get("shots", []))
                with open(bpath) as f:
                    board = json.load(f)
                out.append({"name": name, "board": board, "count": count})
        return jsonify(out)

    @app.route("/api/calib/resume", methods=["POST"])
    def api_calib_resume():
        data = request.get_json(force=True)
        sub_mode = data.get("sub_mode")
        name = data.get("name")
        if sub_mode not in ("intrinsic", "extrinsic") or not name:
            return jsonify({"ok": False, "error": "invalid request"}), 400
        session_dir = os.path.join(CALIB_DIR, sub_mode, name)
        bpath = os.path.join(session_dir, "board_config.json")
        if not os.path.isfile(bpath):
            return jsonify({"ok": False, "error": "세션을 찾을 수 없습니다"}), 404
        with open(bpath) as f:
            cfg = calib_board.parse_board_config(json.load(f))
        rpath = os.path.join(session_dir, "report.json")
        rep = {}
        if os.path.isfile(rpath):
            with open(rpath) as f:
                rep = json.load(f)
        req_devs = [int(x) for x in data.get("devices", [])]
        if sub_mode == "intrinsic":
            cams = rep.get("cameras", {})
            if cams:
                devices = sorted(int(d) for d in cams)
                descs = {d: [r["descriptor"] for r in cams[str(d)]] for d in devices}
                reports = {d: cams[str(d)] for d in devices}
            elif req_devs:
                devices = req_devs[:1]
                descs = {d: [] for d in devices}
                reports = {d: [] for d in devices}
            else:
                return jsonify({"ok": False, "error": "카메라 정보가 없습니다"}), 400
            pair_counts, shots = {}, []
        else:
            pc = rep.get("pair_counts", {})
            if pc:
                pair_counts = {tuple(sorted(int(x) for x in k.split("-"))): v
                               for k, v in pc.items()}
                devices = sorted({d for pair in pair_counts for d in pair})
            elif req_devs:
                devices = req_devs
                pairs = calib_board.adjacent_pairs(devices, bool(data.get("ring", False)))
                pair_counts = {p: 0 for p in pairs}
            else:
                return jsonify({"ok": False, "error": "카메라 정보가 없습니다"}), 400
            descs = {d: [] for d in devices}
            reports = {d: [] for d in devices}
            shots = rep.get("shots", [])
        with state["lock"]:
            state["calib"] = {
                "sub_mode": sub_mode, "cfg": cfg, "devices": devices,
                "ring": bool(data.get("ring", False)), "session_dir": session_dir,
                "descs": descs, "reports": reports, "pair_counts": pair_counts,
                "shots": shots, "pending": None,
            }
            cs = state["calib"]
        resp = {"ok": True, "sub_mode": sub_mode, "board": cfg.to_dict(),
                "session_dir": session_dir, "counts": _calib_counts(cs),
                "devices": devices, "resumed": name}
        if sub_mode == "intrinsic":
            resp["coverage"] = calib_quality.coverage_state(cs["descs"][devices[0]])
        else:
            resp["pairs"] = _pairs_list(cs)
        return jsonify(resp)

    return app
