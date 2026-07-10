# Mode 4 재설계 — 폴더 기반 Intrinsic 계산·검증·보정 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`).
> **Git:** 기존 브랜치 `feat/rectify-mode`에서 계속, **커밋까지만**. merge/push는 사용자.

## Context

**왜 바꾸나.** 현재 Mode 4(보정 확인)는 사용자의 의도와 다르게 동작한다. 사용자가 원하는 것은:
"캘리브레이션 이미지가 저장된 폴더(`captures/calib/intrinsic/<세션>/`)를 지정하면, 그 폴더의 값을 불러오거나
없으면 계산해서 **그 폴더 안에** 저장하고, 그 폴더 기준으로 보정을 시각화"하는 **완전한 폴더 기반** 모드다.

**현재 코드의 문제(탐색으로 확인):**
- Intrinsic이 세션 폴더가 아니라 **전역 활성 디렉터리** `captures/calib/intrinsics/`(복수형)의 `video<dev>.json`에
  저장·소비된다(`_active_intr_path`, `_get_maps`, `api_rectify_intrinsics`). 사용자가 지정한 폴더가 아니라 "코드가
  알아서 불러오는" 구조 — 사용자가 없애고 싶어한 바로 그 모델.
- `_session_dev`가 세션을 **카메라 1대로 축소**한다(첫 카메라만). 한 폴더에 `video0/`,`video3/`가 있어도 하나만 계산.
- 드롭다운(`/api/calib/sessions`)이 `board_config.json`만 있으면 다 나온다 — "계산 가능한 폴더"만 거르지 않음.
- "보정 표시" 토글에 **게이팅이 없다** — intrinsic 유무는 토글 후 텍스트로만 안내.

**사용자 확정 결정(이번 질의응답):**
1. **다중 = 폴더 1개 공유.** 다중 모드는 폴더 드롭다운 1개를 선택하고, 선택한 카메라 전부의 intrinsic이 그 폴더에
   있어야 보정. (Mode 3 intrinsic 세션은 카메라 1대씩이므로, 4대짜리 폴더는 합쳐 만들거나 fake_data로 준비.)
2. **계산 가능 판정 = 이미지 개수(빠름).** `board_config.json`이 있고 `video<n>/`에 jpg가 **4장 이상**이면 후보.
   실제 보드 검출 실패는 '계산' 시 에러로 안내(현재도 `compute_intrinsics`가 4장 미검출 시 ValueError).
3. **파일명 = `video<n>_<model>.json`(모델별).** 예: `video0_pinhole.json`, `video3_fisheye.json`. 카메라당
   pinhole/fisheye 각각 별도 캐시. **세션 폴더 안**에 저장.

**목표 동작(단일/다중 공통 계약):**
- 드롭다운 = `captures/calib/intrinsic/` 아래 **계산 가능한 폴더만**(이름 무관, fake_data 가능).
- "Intrinsic 불러오기/계산" = 선택 폴더의 **모든 `video<n>/`** 에 대해 `video<n>_<model>.json`을 **있으면 로드,
  없으면 계산·저장**. (이미지 있는 카메라만.)
- "보정 표시"는 **선택 카메라와 일치하는 `video<n>_<model>.json`이 존재할 때만** 활성. 단일=선택 카메라 1대,
  다중=선택 카메라별 검증(가진 카메라만 보정, 없는 카메라는 원본+안내).
- 보정 스트림은 **전역 활성본이 아니라 선택한 세션 폴더의 파일**을 사용한다.

**핵심 단순화:** 스트림 URL에 `?session=<이름>&model=<모델>`을 실어 서버가 어느 폴더·모델을 쓸지 URL로 안다
(서버 활성 상태 불필요, 레이스 없음). 다중 on/off만 서버 플래그(`multi_on`)로 유지(지난 연결 고갈 수정 계승 —
토글 시 `<img>` 재생성 금지). 보정 맵 캐시는 `(session, model, dev)` 키.

**범위:** `econ_cam/app.py`(라우트/헬퍼/상태), `econ_cam/static/app.js`(단일·다중 흐름), `econ_cam/templates/index.html`
(다중 폴더·모델 선택 + 토글 게이팅), `scripts/make_fake_intrinsics.py`(세션 폴더 생성으로 변경), 테스트, `docs/USAGE.md`.

**범위 밖(유지):** GStreamer 캡처/스트림 백엔드, Mode 1·2·3, extrinsic 실계산. 전역 `captures/calib/intrinsics/`(복수)
디렉터리는 **더 이상 쓰지 않되 파일 삭제는 안 함**(captures는 복구 불가 — 무단 삭제 금지). 그냥 코드에서 참조 제거.

## 확인된 사실 (현 코드)

- 세션 레이아웃(Mode 3 intrinsic): `captures/calib/intrinsic/<세션>/{board_config.json, report.json, video<n>/frame_NNN.jpg}`.
  `report.json.cameras`는 문자열 dev 키. (`app.py:300-304, 383-392`)
- 보드 로더: `calib_board.parse_board_config(dict) -> BoardConfig` (`calib_board.py:26`). `compute_intrinsics(jpegs, cfg, model)`는
  4장 미검출 시 `ValueError` (`calib_intrinsics.py:120-123`).
- 현 rectify 라우트/헬퍼는 `app.py:542-712`. 상태 `state["rectify"] = {"maps": {}, "session": None, "multi_on": False}`
  (`app.py:80`), `session`은 사용 안 됨(죽은 키). `PREVIEW_WIDTH/HEIGHT` 존재. `stop_sync`가 `multi_on=False` 리셋(`app.py:95`).
- 상수 `INTR_DIR = captures/calib/intrinsics`(`app.py:17`) — rectify에서만 사용. `/api/save`는 `CAPTURE_DIR` 사용(무관).
- 프런트: 단일 `#rect-single-cam/#rect-session/#rect-model/#rect-toggle/#rect-compute/#rect-force/#rect-quality/#rect-orig/#rect-rect`,
  다중 `#rect-multi-cams/#rect-multi-start/#rect-multi-toggle/#rect-multi-grid`(폴더·모델 선택 **없음** → 추가 필요).
  다중 토글은 이미 서버 플래그+캡션만 갱신(연결 재생성 X) — 이 방식 계승.

## File Structure

```
econ_cam/app.py                 # 세션 기반 재설계: _session_devs, /rectify/sessions, compute 루프, session_status,
                                #   스트림 query-param(session,model) + maps 키 (session,model,dev), 전역 활성본 제거
econ_cam/static/app.js          # 단일: 카메라·폴더·모델 독립 + status 기반 토글 게이팅·품질
                                # 다중: 폴더·모델 드롭다운 추가, 그리드 1회 생성, 게이팅, 캡션
econ_cam/templates/index.html   # 다중 폴더/모델 select 추가, 토글 초기 disabled
scripts/make_fake_intrinsics.py # 전역 파일 대신 세션 폴더(fake_data) 생성: board_config + video<n>/더미jpg + video<n>_<model>.json
tests/test_app.py               # sessions 목록/필터, compute 다중카메라, session_status, 스트림 가드, multi_toggle
docs/USAGE.md                   # 폴더 기반 흐름·파일명·게이팅 반영
```

---

### Task 1: 백엔드 — 세션 폴더 기반 재설계

**Files:** `econ_cam/app.py`, `tests/test_app.py`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_app.py`의 기존 rectify 테스트(`test_rectify_compute`,
  `test_rectify_intrinsics_missing`, `test_rectify_stream_404_without_intrinsics`, `test_rectify_intrinsics_quality_fields`,
  `test_rectify_compute_empty_folder_returns_400`, `test_intrinsics_reports_source_session`,
  `test_rectify_session_intrinsics_load_only`)를 **아래 새 테스트로 교체**한다(전역 INTR_DIR/`_active`/`source_session`/
  구 `session_intrinsics` 참조 제거). `test_rectify_multi_toggle`·`test_single_stream_blocked_while_sync_active`는 유지.

```python
def _make_session(tmp_path, sub_mode="intrinsic", name="s1", devs=(0,), n_img=4):
    sess = tmp_path / sub_mode / name
    sess.mkdir(parents=True)
    (sess / "board_config.json").write_text(json.dumps(
        {"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25.0}))
    for d in devs:
        (sess / f"video{d}").mkdir()
        for i in range(n_img):
            (sess / f"video{d}" / f"frame_{i:03d}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    return sess


def test_rectify_sessions_lists_only_calibratable(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    _make_session(tmp_path, name="good", devs=(0, 3), n_img=4)     # 후보
    _make_session(tmp_path, name="toofew", devs=(1,), n_img=2)     # jpg<4 → 제외
    empty = tmp_path / "intrinsic" / "nocfg"; (empty / "video0").mkdir(parents=True)  # board_config 없음 → 제외
    client = app_module.create_app().test_client()
    body = client.get("/api/rectify/sessions?sub_mode=intrinsic").get_json()
    names = {s["name"]: s for s in body}
    assert set(names) == {"good"}
    assert names["good"]["devs"] == [0, 3]


def test_rectify_compute_per_camera(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    _make_session(tmp_path, name="s1", devs=(0, 3))
    fake = ci.Intrinsics(model="pinhole", K=[[1,0,0],[0,1,0],[0,0,1]], dist=[0]*5,
                         image_size=(1280,720), rms=0.3, per_view_errors=[0.3]*4,
                         n_images=4, board={"board_type": "checkerboard"})
    monkeypatch.setattr(app_module.calib_intrinsics, "compute_intrinsics", lambda *a, **k: fake)
    client = app_module.create_app().test_client()
    r = client.post("/api/rectify/compute", json={"session": "s1", "model": "pinhole"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] and set(body["cameras"]) == {"0", "3"}
    assert body["cameras"]["0"]["rms"] == 0.3 and body["cameras"]["0"]["verdict"]["level"] == "excellent"
    assert os.path.exists(str(tmp_path / "intrinsic" / "s1" / "video0_pinhole.json"))
    assert os.path.exists(str(tmp_path / "intrinsic" / "s1" / "video3_pinhole.json"))
    r2 = client.post("/api/rectify/compute", json={"session": "s1", "model": "pinhole"})
    assert r2.get_json()["cameras"]["0"]["cached"] is True


def test_rectify_compute_empty_folder_400(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    sess = tmp_path / "intrinsic" / "empty"; sess.mkdir(parents=True)
    (sess / "board_config.json").write_text(json.dumps(
        {"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25.0}))
    client = app_module.create_app().test_client()
    r = client.post("/api/rectify/compute", json={"session": "empty", "model": "pinhole"})
    assert r.status_code == 400 and r.get_json()["ok"] is False


def test_rectify_session_status(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    sess = _make_session(tmp_path, name="s1", devs=(0, 3))
    intr = ci.Intrinsics(model="pinhole", K=[[1000,0,960],[0,1000,540],[0,0,1]],
                         dist=[-0.3,0.1,0,0,0], image_size=(1920,1080), rms=0.62,
                         per_view_errors=[0.4,0.55,1.8], n_images=3, board={"board_type": "checkerboard"})
    ci.save_intrinsics(str(sess / "video0_pinhole.json"), intr)     # video0만 계산됨
    client = app_module.create_app().test_client()
    body = client.get("/api/rectify/session_status?session=s1&model=pinhole").get_json()
    assert body["cameras"]["0"]["has"] is True and body["cameras"]["0"]["verdict"]["level"] == "good"
    assert body["cameras"]["0"]["K"][0][0] == 1000
    assert body["cameras"]["3"]["has"] is False


def test_rectify_stream_needs_session_and_intrinsic(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CALIB_DIR", str(tmp_path))
    _make_session(tmp_path, name="s1", devs=(0,))
    client = app_module.create_app().test_client()
    assert client.get("/api/rectify/stream/0").status_code == 404              # session 파라미터 없음
    r = client.get("/api/rectify/stream/0?session=s1&model=pinhole")
    assert r.status_code == 404 and "intrinsic" in r.get_data(as_text=True)    # 파일 없음


def test_rectify_sync_stream_404_without_session():
    client = app_module.create_app().test_client()
    assert client.get("/api/rectify/sync/stream/0?session=s1&model=pinhole").status_code == 404
```
Run: `.venv/bin/python -m pytest tests/test_app.py -q` → 새 테스트 FAIL.

- [ ] **Step 2: 헬퍼 교체** — `app.py:544-571`의 `_session_dev`/`_active_intr_path`를 제거하고, `_session_dir`·
  `_load_session_jpegs`는 유지, `_session_devs`·`_intr_path` 추가:

```python
    def _session_dir(sub_mode, name):
        return os.path.join(CALIB_DIR, sub_mode, name)

    def _session_devs(session_dir, min_images=4):
        """video<n>/ 서브폴더 중 jpg가 min_images장 이상인 카메라 번호(정렬)."""
        devs = []
        if not os.path.isdir(session_dir):
            return devs
        for n in sorted(os.listdir(session_dir)):
            p = os.path.join(session_dir, n)
            if n.startswith("video") and os.path.isdir(p):
                n_jpg = sum(1 for f in os.listdir(p) if f.endswith(".jpg"))
                if n_jpg >= min_images:
                    try:
                        devs.append(int(n[len("video"):]))
                    except ValueError:
                        pass
        return devs

    def _intr_path(session_dir, dev, model):
        return os.path.join(session_dir, f"video{dev}_{model}.json")

    def _load_session_jpegs(session_dir, dev):   # (기존 유지)
        ...
```

- [ ] **Step 3: 세션 목록 라우트 추가**(계산 가능 폴더만) — rectify 블록 앞부분에:

```python
    @app.route("/api/rectify/sessions")
    def api_rectify_sessions():
        sub_mode = request.args.get("sub_mode", "intrinsic")
        base = os.path.join(CALIB_DIR, sub_mode)
        out = []
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                sdir = os.path.join(base, name)
                if not os.path.isdir(sdir):
                    continue
                if not os.path.exists(os.path.join(sdir, "board_config.json")):
                    continue
                devs = _session_devs(sdir)
                if devs:
                    out.append({"name": name, "devs": devs})
        return jsonify(out)
```

- [ ] **Step 4: compute 라우트 교체**(모든 카메라 루프, 세션 폴더에 `video<n>_<model>.json` 저장, 전역본 없음) —
  `app.py:573-612`를 교체:

```python
    @app.route("/api/rectify/compute", methods=["POST"])
    def api_rectify_compute():
        body = request.get_json(force=True)
        sub_mode = body.get("sub_mode", "intrinsic")
        name = body["session"]
        model = body.get("model", "pinhole")
        force = bool(body.get("force"))
        session_dir = _session_dir(sub_mode, name)
        if not os.path.isdir(session_dir):
            return jsonify({"ok": False, "error": "세션 없음"}), 404
        devs = _session_devs(session_dir)
        if not devs:
            return jsonify({"ok": False, "error": "폴더에 계산 가능한 카메라 이미지가 없습니다"}), 400
        cfg = None
        cameras, errors = {}, {}
        for dev in devs:
            path = _intr_path(session_dir, dev, model)
            try:
                if os.path.exists(path) and not force:
                    intr = calib_intrinsics.load_intrinsics(path); cached = True
                else:
                    if cfg is None:
                        with open(os.path.join(session_dir, "board_config.json")) as f:
                            cfg = calib_board.parse_board_config(json.load(f))
                    intr = calib_intrinsics.compute_intrinsics(
                        _load_session_jpegs(session_dir, dev), cfg, model=model)
                    calib_intrinsics.save_intrinsics(path, intr); cached = False
                cameras[str(dev)] = {"rms": intr.rms, "per_view_errors": intr.per_view_errors,
                                     "n_images": intr.n_images, "image_size": list(intr.image_size),
                                     "K": intr.K, "dist": intr.dist, "cached": cached,
                                     "verdict": calib_quality.intrinsic_verdict(intr.rms)}
                with state["lock"]:
                    state["rectify"]["maps"].pop((name, model, dev), None)
            except (ValueError, OSError) as e:
                errors[str(dev)] = str(e)
        return jsonify({"ok": True, "session": name, "model": model,
                        "cameras": cameras, "errors": errors})
```

- [ ] **Step 5: `intrinsics/<dev>` + `session_intrinsics` 제거, `session_status` 추가** —
  `app.py:614-646`(두 라우트)를 삭제하고 하나로:

```python
    @app.route("/api/rectify/session_status")
    def api_rectify_session_status():
        """선택 폴더+모델에서 카메라별 intrinsic 유무·품질을 '계산 없이' 반환(게이팅·품질·캡션용)."""
        name = request.args.get("session")
        sub_mode = request.args.get("sub_mode", "intrinsic")
        model = request.args.get("model", "pinhole")
        if not name:
            return jsonify({"session": None, "model": model, "cameras": {}})
        session_dir = _session_dir(sub_mode, name)
        cams = {}
        for dev in _session_devs(session_dir):
            path = _intr_path(session_dir, dev, model)
            if os.path.exists(path):
                intr = calib_intrinsics.load_intrinsics(path)
                cams[str(dev)] = {"has": True, "model": intr.model, "rms": intr.rms,
                                  "per_view_errors": intr.per_view_errors, "n_images": intr.n_images,
                                  "image_size": list(intr.image_size), "K": intr.K, "dist": intr.dist,
                                  "verdict": calib_quality.intrinsic_verdict(intr.rms)}
            else:
                cams[str(dev)] = {"has": False}
        return jsonify({"session": name, "model": model, "cameras": cams})
```

- [ ] **Step 6: `_get_maps`를 (session_dir,dev,model,key) 기반으로 교체** — `app.py:648-662`:

```python
    def _get_maps(session_dir, dev, model, cache_key):
        with state["lock"]:
            m = state["rectify"]["maps"].get(cache_key)
        if m is not None:
            return m
        path = _intr_path(session_dir, dev, model)
        if not os.path.exists(path):
            return None
        intr = calib_intrinsics.load_intrinsics(path)
        maps = calib_intrinsics.build_undistort_maps(intr, (PREVIEW_WIDTH, PREVIEW_HEIGHT))
        with state["lock"]:
            state["rectify"]["maps"][cache_key] = maps
        return maps
```

- [ ] **Step 7: 두 스트림 라우트를 query-param(session,model) 기반으로 교체** — `app.py:664-707`:

```python
    @app.route("/api/rectify/stream/<int:dev>")
    def api_rectify_stream(dev):
        if state["sync_session"] is not None:
            return ("동기 세션 활성 중 — 단일 스트림 불가", 409)
        name = request.args.get("session")
        model = request.args.get("model", "pinhole")
        sub_mode = request.args.get("sub_mode", "intrinsic")
        if not name:
            return ("session 필요", 404)
        maps = _get_maps(_session_dir(sub_mode, name), dev, model, (name, model, dev))
        if maps is None:
            return ("intrinsic 없음", 404)
        with state["lock"]:
            cam = get_or_start_stream(dev)

        def gen():
            while state["streams"].get(dev) is cam:
                jpeg = cam.latest_jpeg()
                if jpeg is None:
                    continue
                out = calib_intrinsics.rectify_jpeg(jpeg, maps)
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + out + b"\r\n")
                time.sleep(1 / 15)

        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/api/rectify/sync/stream/<int:dev>")
    def api_rectify_sync_stream(dev):
        sess = state["sync_session"]
        if sess is None:
            return ("", 404)
        name = request.args.get("session")
        model = request.args.get("model", "pinhole")
        sub_mode = request.args.get("sub_mode", "intrinsic")
        session_dir = _session_dir(sub_mode, name) if name else None

        def gen():
            last = None
            while state["sync_session"] is sess:
                jpeg = sess.latest_jpeg(dev)
                if jpeg is not None and jpeg is not last:
                    last = jpeg
                    out = jpeg
                    if state["rectify"]["multi_on"] and session_dir:
                        maps = _get_maps(session_dir, dev, model, (name, model, dev))
                        if maps is not None:
                            out = calib_intrinsics.rectify_jpeg(jpeg, maps)
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + out + b"\r\n")
                time.sleep(0.02)

        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")
```
  `multi_toggle` 라우트(`app.py:709-712`)는 그대로 유지.

- [ ] **Step 8: 상태·상수 정리** — `state["rectify"]`(`app.py:80`)를 `{"maps": {}, "multi_on": False}`로(죽은 `session`
  키 제거). 상수 `INTR_DIR`(`app.py:17`) 및 남은 참조 전부 제거(전역 활성본 폐기 — 디스크 파일은 삭제하지 않음).
  `git grep -n INTR_DIR econ_cam/` 로 잔여 참조 0 확인.

- [ ] **Step 9: 통과 확인** — Run: `.venv/bin/python -m pytest tests/test_app.py -q` → PASS(회귀 없음).

- [ ] **Step 10: 커밋**

```bash
git add econ_cam/app.py tests/test_app.py
git commit -m "feat(rectify): folder-driven intrinsics — session-local video<n>_<model>.json, calibratable listing, per-camera compute, session-scoped streams (drop global active dir)"
```

---

### Task 2: 프런트 — 단일 서브모드(카메라·폴더·모델 독립 + 게이팅)

**Files:** `econ_cam/static/app.js`, `econ_cam/templates/index.html`

계약: 사용자가 **카메라(라이브 소스)·폴더·모델**을 각각 고른다. "Intrinsic 불러오기/계산"은 폴더의 모든 카메라를
처리한다. **선택 카메라의 `video<sel>_<model>.json`이 존재할 때만** "보정 표시" 토글이 활성화되고, 켜면 오른쪽에
그 파일로 보정한 라이브가 나온다. 품질 패널은 **선택 카메라**의 값을 보여준다.

- [ ] **Step 1: index.html — 단일 토글 초기 비활성.**
  `#rect-toggle`(index.html:193) 체크박스에 `disabled` 속성 추가, 라벨 옆에 `<span id="rect-toggle-hint" class="hint"></span>` 추가(게이팅 사유 안내용).

- [ ] **Step 2: app.js — 세션 드롭다운을 새 라우트로.** `populateRectSessions()`를 교체:

```js
let rectSessions = {};   // name -> devs[]
async function populateRectSessions() {
  const list = await api("/api/rectify/sessions?sub_mode=intrinsic");
  rectSessions = {};
  list.forEach((s) => (rectSessions[s.name] = s.devs));
  const opts = list.map((s) => `<option value="${s.name}">${s.name} (cam ${s.devs.join(",")})</option>`).join("");
  ["rect-session", "rect-multi-session"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = opts || `<option value="">(계산 가능한 폴더 없음)</option>`;
  });
}
```

- [ ] **Step 3: app.js — compute를 카메라별 응답으로.** `computeRectIntrinsics()`를 교체(자동 카메라 설정 제거,
  계산 후 상태 갱신):

```js
async function computeRectIntrinsics() {
  const session = document.getElementById("rect-session").value;
  const model = document.getElementById("rect-model").value;
  const force = document.getElementById("rect-force").checked;
  if (!session) return;
  const st = document.getElementById("rect-status");
  st.textContent = "계산 중…";
  try {
    const r = await jsonPost("/api/rectify/compute", { session, model, force });
    if (!r.ok) { st.textContent = "오류: " + (r.error || "실패"); return; }
    const done = Object.keys(r.cameras);
    const err = Object.entries(r.errors || {}).map(([d, m]) => `video${d}: ${m}`);
    st.textContent = `완료 — intrinsic: ${done.map((d) => "video" + d).join(", ") || "없음"}`
      + (err.length ? ` · 실패 ${err.join("; ")}` : "");
    await refreshRectSingleStatus();     // 게이팅·품질 갱신
  } catch (e) {
    st.textContent = "오류: " + e.message;
  }
}
```

- [ ] **Step 4: app.js — 상태 기반 게이팅+품질.** `loadSessionIntrinsic`/`updateRectSingleRight` 대신
  `refreshRectSingleStatus()` 하나로 통합. 카메라/폴더/모델/토글 변경 시 호출:

```js
let rectSingleStatus = {};   // 현재 선택 폴더+모델의 카메라별 상태
async function refreshRectSingleStatus() {
  const dev = document.getElementById("rect-single-cam").value;
  const session = document.getElementById("rect-session").value;
  const model = document.getElementById("rect-model").value;
  const toggle = document.getElementById("rect-toggle");
  const hint = document.getElementById("rect-toggle-hint");
  rectSingleStatus = session
    ? (await api(`/api/rectify/session_status?session=${encodeURIComponent(session)}&model=${model}`)).cameras
    : {};
  const info = dev === "" ? undefined : rectSingleStatus[dev];
  const ready = !!(info && info.has);
  toggle.disabled = !ready;
  if (!ready) { toggle.checked = false; }
  hint.textContent = ready ? "" :
    (dev === "" ? "카메라를 선택하세요" :
     !session ? "폴더를 선택하세요" :
     `video${dev} intrinsic 없음 — 이 폴더에서 계산 필요`);
  if (ready && info) renderRectQuality(info, { session, dev, model });
  else document.getElementById("rect-quality").hidden = true;
  updateRectSingleRight();
}

function updateRectSingleRight() {
  const dev = document.getElementById("rect-single-cam").value;
  const session = document.getElementById("rect-session").value;
  const model = document.getElementById("rect-model").value;
  const t = document.getElementById("rect-toggle");
  const on = t.checked && !t.disabled;
  const img = document.getElementById("rect-rect");
  const msg = document.getElementById("rect-rect-msg");
  if (on && dev !== "" && session) {
    img.src = `/api/rectify/stream/${dev}?session=${encodeURIComponent(session)}&model=${model}`;
    img.hidden = false; msg.hidden = true;
  } else {
    img.removeAttribute("src"); img.hidden = true;
    msg.hidden = false; msg.textContent = "보정 표시를 켜면 오른쪽에 보정된 영상이 나옵니다.";
  }
}
```
  `previewRectSingle()`(왼쪽 원본 라이브)는 유지하되 오른쪽 갱신을 `refreshRectSingleStatus()`로:
```js
function previewRectSingle() {
  const dev = document.getElementById("rect-single-cam").value;
  if (dev !== "") document.getElementById("rect-orig").src = `/api/stream/${dev}/mjpeg`;
  refreshRectSingleStatus();
}
function startRectSingle() { previewRectSingle(); }
```
  `renderRectQuality(info, ctx)`는 기존 함수 재사용(입력 필드 `rms/per_view_errors/verdict/K/dist`가 그대로 있음).
  `info.dev` 대신 `ctx.dev` 사용하도록 호출부 정리, `ctx.source`는 `ctx.session` 사용.

- [ ] **Step 5: app.js — 이벤트 배선 갱신(단일).** bootstrap에서:
  - `#rect-single-cam` change → `previewRectSingle()`
  - `#rect-session` change → `refreshRectSingleStatus()`
  - `#rect-model` change → `refreshRectSingleStatus()`
  - `#rect-toggle` change → `updateRectSingleRight()`
  - `#rect-compute` click → `computeRectIntrinsics()`
  (기존 `loadSessionIntrinsic` 호출 제거.)

- [ ] **Step 6: 회귀 확인** — Run: `.venv/bin/python -m pytest -q` → PASS. 수동: 단일에서 폴더·카메라·모델 조합에
  따라 토글이 활성/비활성 되고, 켜면 좌(원본)/우(보정) 표시.

- [ ] **Step 7: 커밋**

```bash
git add econ_cam/static/app.js econ_cam/templates/index.html
git commit -m "feat(rectify): single mode — independent cam/folder/model, status-gated toggle, per-camera quality"
```

---

### Task 3: 프런트 — 다중 서브모드(폴더 1개 공유 + 게이팅 + 캡션)

**Files:** `econ_cam/templates/index.html`, `econ_cam/static/app.js`

계약(사용자 결정): 카메라 체크 → 라이브 → **폴더 드롭다운 1개 + 모델 선택** → 선택 카메라별로 그 폴더에
`video<d>_<model>.json`이 있는지 검증. 가진 카메라만 보정, 없는 카메라는 원본+캡션 안내. 토글은 **연결 재생성 없이**
서버 플래그만 전환(지난 고갈 버그 수정 계승).

- [ ] **Step 1: index.html — 다중에 폴더·모델 select 추가 + 토글 초기 비활성.**
  `#rectify-multi`(index.html:217-227) 안, 카메라 체크박스 아래에:
```html
<label>폴더 <select id="rect-multi-session"></select></label>
<label>모델
  <select id="rect-multi-model">
    <option value="pinhole">pinhole</option>
    <option value="fisheye">fisheye</option>
  </select>
</label>
```
  `#rect-multi-toggle`에 `disabled` 추가.

- [ ] **Step 2: app.js — startRectMulti에 폴더·모델 반영 + 게이팅.**

```js
function rectMultiModel() { return document.getElementById("rect-multi-model").value; }
function rectMultiSession() { return document.getElementById("rect-multi-session").value; }

async function startRectMulti() {
  const devs = selectedRectMultiDevs();
  if (!devs.length) return;
  await jsonPost("/api/sync/start", { devices: devs, sync_mode: 1 });
  await jsonPost("/api/rectify/multi_toggle", { on: rectMultiOn() });
  await buildRectMultiGrid(devs);
}

async function buildRectMultiGrid(devs) {
  const session = rectMultiSession(), model = rectMultiModel();
  rectMultiInfo = session
    ? (await api(`/api/rectify/session_status?session=${encodeURIComponent(session)}&model=${model}`)).cameras
    : {};
  const t = Date.now();
  const q = session ? `?session=${encodeURIComponent(session)}&model=${model}&t=${t}` : `?t=${t}`;
  document.getElementById("rect-multi-grid").innerHTML = devs
    .map((d) => `<figure><img id="rect-m-${d}" src="/api/rectify/sync/stream/${d}${q}">`
      + `<figcaption id="rect-m-cap-${d}"></figcaption></figure>`)
    .join("");
  updateRectMultiCaptions(devs);
  gateRectMultiToggle(devs);
}

function gateRectMultiToggle(devs) {
  const any = devs.some((d) => rectMultiInfo[String(d)]?.has);
  const t = document.getElementById("rect-multi-toggle");
  t.disabled = !any;
  if (!any) t.checked = false;
}

function multiCaptionText(d) {
  const info = rectMultiInfo[String(d)] || {};
  const on = rectMultiOn();
  if (info.has)
    return `video${d} (${on ? "보정" : "원본"}) · ${info.model} RMS ${Number(info.rms).toFixed(2)}`;
  return `video${d} (원본) · intrinsic 없음 — 이 폴더에서 계산 필요`;
}
function updateRectMultiCaptions(devs) {
  devs.forEach((d) => {
    const cap = document.getElementById(`rect-m-cap-${d}`);
    if (cap) cap.textContent = multiCaptionText(d);
  });
}
```

- [ ] **Step 3: app.js — 이벤트 배선(다중).** bootstrap에서:
  - `#rect-multi-start` click → `startRectMulti`
  - `#rect-multi-cams` change → `stopSync().then(startRectMulti)`(구성 바뀌면 세션+그리드 재생성 — 유지)
  - `#rect-multi-session` change → `stopSync().then(startRectMulti)`(스트림 URL의 session이 바뀌므로 재생성 필요)
  - `#rect-multi-model` change → `stopSync().then(startRectMulti)`(동일)
  - `#rect-multi-toggle` change → `POST /api/rectify/multi_toggle` 후 `updateRectMultiCaptions(selectedRectMultiDevs())`
    (연결 재생성 없음 — 내용만 서버에서 원본↔보정 전환)
  - 모드 진입 `startRectify()`는 `populateRectSessions()`가 다중 드롭다운도 채우도록(Task2 Step2에서 처리됨).

- [ ] **Step 4: 회귀 확인** — Run: `.venv/bin/python -m pytest -q` → PASS. 수동: 다중에서 폴더·모델 선택 후 토글을
  여러 번 눌러도 4대 유지되고, intrinsic 가진 카메라만 보정·나머지는 원본+안내.

- [ ] **Step 5: 커밋**

```bash
git add econ_cam/static/app.js econ_cam/templates/index.html
git commit -m "feat(rectify): multi mode — shared folder+model dropdown, per-camera validation, gated stable toggle"
```

---

### Task 4: 가짜 intrinsic 생성기 — 세션 폴더 방식으로

**Files:** `scripts/make_fake_intrinsics.py`

파이프라인을 실제 캘리브레이션 없이 검증할 수 있도록, 전역 파일 대신 **완전한 세션 폴더**를 만든다:
드롭다운에 뜨고(=board_config + video<n>/ 더미 jpg 4장), "불러오기" 시 미리 놓인 `video<n>_<model>.json`을 로드.

- [ ] **Step 1: 스크립트 교체.** `fake_intrinsics(dev, model, width, height)`(K + 배럴 왜곡 k1=-0.30)는 재사용하되,
  출력 대상을 세션 폴더로:

```python
def make_fake_session(session, devs, model, width, height):
    base = os.path.join("captures", "calib", "intrinsic", session)
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "board_config.json"), "w") as f:
        json.dump({"board_type": "checkerboard", "cols": 10, "rows": 7, "square_mm": 25.0}, f, indent=2)
    for dev in devs:
        vd = os.path.join(base, f"video{dev}")
        os.makedirs(vd, exist_ok=True)
        for i in range(4):                       # ≥4장이라야 드롭다운 후보(이미지 개수 판정)
            open(os.path.join(vd, f"frame_{i:03d}.jpg"), "wb").write(b"\xff\xd8\xff\xd9")
        intr = fake_intrinsics(dev, model, width, height)
        save_intrinsics(os.path.join(base, f"video{dev}_{model}.json"), intr)
    print(f"생성: {base}  (cam {devs}, model={model})")
```
  argparse: `--session fake_data --devs 0 1 2 3 --model pinhole --width 1920 --height 1080`.
  (더미 jpg는 실제 디코드가 안 되므로 '재계산'은 실패한다 — 로드 경로 테스트용임을 스크립트 주석·`--help`에 명시.)

- [ ] **Step 2: 실행 확인** — Run:
  `.venv/bin/python scripts/make_fake_intrinsics.py --session fake_data --devs 0 1 2 3 --model pinhole`
  → `captures/calib/intrinsic/fake_data/`에 board_config.json, video0..3/, video0..3_pinhole.json 생성.
  (서버 실행 시) `/api/rectify/sessions?sub_mode=intrinsic`에 fake_data(cam 0,1,2,3) 표시 확인.

- [ ] **Step 3: 커밋**

```bash
git add scripts/make_fake_intrinsics.py
git commit -m "chore(rectify): fake generator builds a full session folder (video<n>_<model>.json)"
```

---

### Task 5: 문서 갱신

**Files:** `docs/USAGE.md`

- [ ] **Step 1: Mode 4 절 재작성.** 핵심을 반영:
  - `captures/calib/intrinsic/` 아래 **계산 가능 폴더**(board_config.json + `video<n>/` jpg ≥4장)만 드롭다운에 뜬다(폴더명 무관, fake_data 가능).
  - "Intrinsic 불러오기/계산" = 폴더의 **모든 `video<n>/`** 에 대해 `video<n>_<model>.json`을 로드/계산·저장(세션 폴더 안). 이미지 있는 카메라만.
  - "보정 표시"는 **선택 카메라와 일치하는 `video<n>_<model>.json`이 있을 때만** 활성(단일=1대, 다중=카메라별 검증).
  - 다중은 **폴더 1개 공유 + 모델 선택**; 가진 카메라만 보정, 없는 카메라는 원본+안내. 토글은 스트림 재생성 없이 내용만 전환.
  - 가짜 생성기(`scripts/make_fake_intrinsics.py --session fake_data …`)로 실제 캘리브레이션 없이 파이프라인 시험 가능.
  - 전역 `captures/calib/intrinsics/`(복수) 활성본 개념은 폐기됨(폴더 기반으로 대체).

- [ ] **Step 2: 커밋**

```bash
git add docs/USAGE.md
git commit -m "docs: Mode 4 folder-driven intrinsics (per-model files, gating, shared multi folder)"
```

---

## Verification

**자동:** `.venv/bin/python -m pytest -q` — 신규 rectify 테스트(sessions 필터, per-camera compute, session_status,
스트림 가드, multi_toggle, 싱크중 단일 409) 전부 PASS + 기존 회귀 없음. `git grep -n INTR_DIR econ_cam/` → 0.

**수동 (`run.py` → "보정 확인"):**
1. 진입 시 드롭다운에 **계산 가능한 폴더만** 뜨고, 각 폴더에 포함 카메라(`cam 0,3`)가 표시된다.
2. (단일) 카메라·폴더·모델을 고른다. 폴더에 그 카메라 intrinsic이 없으면 "불러오기/계산"을 눌러 계산 → 세션 폴더에
   `video<n>_<model>.json` 생성. 계산 후 토글이 활성화되고, 켜면 좌(원본)/우(보정) 표시. 다른 카메라·모델을 고르면
   토글이 다시 게이팅된다(일치하는 파일 있을 때만 활성).
3. (다중) 카메라 체크 + 폴더 + 모델 선택 → 라이브 그리드. intrinsic 가진 카메라만 보정되고, 없는 카메라는 원본 +
   "intrinsic 없음" 캡션. **보정 표시 토글을 여러 번 눌러도 4대 유지**되고 재감지·모드 전환 정상(지난 고갈 버그 무재발).
4. `make_fake_intrinsics.py --session fake_data …` 실행 후 fake_data 폴더로 단일/다중 보정이 로드 경로로 즉시 동작.
5. 파일명이 모델별(`video0_pinhole.json` / `video0_fisheye.json`)로 분리 저장된다.

## 주의 (구현자)

- **폴더가 진실의 원천.** intrinsic은 세션 폴더 안 `video<n>_<model>.json`에만 저장/소비. 전역 활성 디렉터리 없음.
  스트림은 URL `?session=&model=`로 어느 폴더·모델인지 안다(서버 활성 상태 불필요).
- **다중 토글은 연결 재생성 금지**(서버 플래그만). 폴더·모델·카메라 구성 변경 시에만 그리드/세션 재생성.
- **captures 삭제 금지**(복구 불가). 구 전역 `intrinsics/`(복수) 파일은 남겨두고 코드 참조만 제거.
- 스트리밍 200 경로는 무한 제너레이터라 pytest 검증 불가 → 수동 확인. 자동 테스트는 목록/필터/compute/status/가드/토글.
- Git: `feat/rectify-mode`에서 커밋만. develop/main merge·push는 사용자.
- `Intrinsics.source_session` 필드는 이제 안 쓰지만 **제거하지 않는다**(기존 파일 로드 호환 — 기본값 `""`).
