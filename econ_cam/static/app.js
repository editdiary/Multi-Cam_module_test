"use strict";

const api = (p, opts) => fetch(p, opts).then((r) => r.json());
const jsonPost = (p, body) =>
  api(p, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

let cameras = [];

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2500);
}

let statusTimer = null;

async function stopStreams() {
  document.getElementById("single-preview").src = "";
  await fetch("/api/stream/stop", { method: "POST" });
}

async function stopSync() {
  if (statusTimer) {
    clearInterval(statusTimer);
    statusTimer = null;
  }
  document.querySelectorAll("#multi-grid img").forEach((i) => (i.src = ""));
  await fetch("/api/sync/stop", { method: "POST" });
}

function setMode(mode) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.mode === mode)
  );
  document.querySelectorAll(".mode").forEach((s) =>
    s.classList.toggle("active", s.id === mode)
  );
  Promise.all([stopStreams(), stopSync(), stopCalib(), stopRectify()]).then(() => {
    if (mode === "single") startSinglePreview();
    if (mode === "multi") startSyncSession();
    if (mode === "calib") startCalib();
    if (mode === "rectify") startRectify();
  });
}

function activeMode() {
  return document.querySelector(".tab.active").dataset.mode;
}

function currentResolution() {
  const v = document.getElementById("resolution").value;  // "1280x720"
  return v ? v.split("x").map(Number) : null;
}

function renderSingleStatus(captured) {
  const el = document.getElementById("single-status");
  const r = currentResolution();
  const orig = r ? `${r[0]}×${r[1]}` : "—";
  if (captured) {
    el.className = "status-line captured";
    el.textContent = `📸 촬영 완료 · 원본 ${orig} 해상도로 저장 준비됨 — Save를 누르세요`;
  } else {
    el.className = "status-line";
    el.innerHTML = `<span style="color:#2d7">●</span> 라이브 · 프리뷰 640×360 ~15fps · 촬영 시 원본 ${orig} 해상도로 저장`;
  }
}

async function loadCameras() {
  cameras = await api("/api/cameras");
  document.getElementById("single-cam").innerHTML = cameras
    .map((c) => `<option value="${c.dev}">${c.label}</option>`)
    .join("");
  document.getElementById("multi-cams").innerHTML = cameras
    .map(
      (c) =>
        `<label><input type="checkbox" value="${c.dev}" checked> ${c.label}</label>`
    )
    .join("");
  document.getElementById("calib-int-cam").innerHTML = cameras
    .map((c) => `<option value="${c.dev}">${c.label}</option>`)
    .join("");
  document.getElementById("calib-ext-cams").innerHTML = cameras
    .map(
      (c) =>
        `<label title="${c.label}"><input type="checkbox" value="${c.dev}" checked> video${c.dev}</label>`
    )
    .join("");
}

async function loadResolutions() {
  if (!cameras.length) return;
  const [list, cur] = await Promise.all([
    api(`/api/resolutions?dev=${cameras[0].dev}`),
    api("/api/resolution"),
  ]);
  const sel = document.getElementById("resolution");
  sel.innerHTML = list
    .map(([w, h]) => {
      const on = w === cur.width && h === cur.height ? " selected" : "";
      return `<option value="${w}x${h}"${on}>${w}×${h}</option>`;
    })
    .join("");
}

async function applyResolution() {
  const [w, h] = document.getElementById("resolution").value.split("x").map(Number);
  await jsonPost("/api/resolution", { width: w, height: h });
  setMode(activeMode()); // 스트림/세션 재시작(백엔드가 stop_streams+stop_sync 처리)
}

function startSinglePreview() {
  const dev = document.getElementById("single-cam").value;
  if (!dev) return;
  const still = document.getElementById("single-still");
  still.hidden = true;
  const img = document.getElementById("single-preview");
  img.hidden = false;
  img.src = `/api/stream/${dev}/mjpeg?t=${Date.now()}`;
  document.getElementById("single-live").disabled = true;
  renderSingleStatus(false);
}

async function singleCapture() {
  const dev = document.getElementById("single-cam").value;
  let data;
  try {
    data = await jsonPost("/api/capture", { mode: "single", devices: [dev] });
  } catch (e) {
    toast("촬영 실패");
    return;
  }
  if (!data.images || !data.images[dev]) {
    toast("촬영 실패");
    return;
  }
  const still = document.getElementById("single-still");
  still.src = data.images[dev];
  still.hidden = false;
  document.getElementById("single-preview").hidden = true;
  document.getElementById("single-live").disabled = false;
  renderSingleStatus(true);
  toast("촬영 완료");
}

async function save() {
  const r = await api("/api/save", { method: "POST" });
  toast(r.ok ? `저장됨: ${r.path}` : `저장 실패: ${r.error}`);
}

function selectedMultiDevs() {
  return [...document.querySelectorAll("#multi-cams input:checked")].map(
    (c) => c.value
  );
}

async function startSyncSession() {
  const devs = selectedMultiDevs();
  if (!devs.length) {
    renderSyncStatus(null);
    document.getElementById("multi-grid").innerHTML = "";
    return;
  }
  await jsonPost("/api/sync/start", { devices: devs, sync_mode: 1 });
  document.getElementById("multi-grid").innerHTML = devs
    .map(
      (d) =>
        `<figure><img id="sync-img-${d}" src="/api/sync/stream/${d}?t=${Date.now()}">` +
        `<figcaption id="sync-cap-${d}">video${d}</figcaption></figure>`
    )
    .join("");
  document.getElementById("multi-live").disabled = true;
  if (statusTimer) clearInterval(statusTimer);
  statusTimer = setInterval(pollSyncStatus, 700);
}

async function pollSyncStatus() {
  const s = await api("/api/sync/status");
  renderSyncStatus(s && s.ready ? s : null);
}

function renderSyncStatus(s) {
  const el = document.getElementById("multi-status");
  if (!s) {
    el.className = "status-line";
    el.textContent = "동기화 측정 준비 중…";
    return;
  }
  const spread = s.spread_ms;
  const level = spread < 2 ? "good" : spread < 10 ? "warn" : "bad";
  const dot = { good: "🟢", warn: "🟡", bad: "🔴" }[level];
  const word = { good: "동기 양호", warn: "동기 주의", bad: "동기 불량" }[level];
  el.className = "status-line " + level;
  el.textContent = `${dot} ${word}   최대편차 ${spread.toFixed(2)} ms · σ ${s.std_ms.toFixed(2)} ms · 기준 video${s.ref_dev}`;
}

async function multiCapture() {
  if (!selectedMultiDevs().length) {
    toast("카메라를 선택하세요");
    return;
  }
  toast("동기 촬영 중...");
  let data;
  try {
    data = await jsonPost("/api/sync/capture", {});
  } catch (e) {
    toast("동기 촬영 실패");
    return;
  }
  if (!data.images) {
    toast("동기 촬영 실패");
    return;
  }
  if (statusTimer) {
    clearInterval(statusTimer); // 그리드 고정(freeze)
    statusTimer = null;
  }
  const per = data.stats.per_camera;
  Object.entries(data.images).forEach(([dev, uri]) => {
    document.getElementById(`sync-img-${dev}`).src = uri;
    document.getElementById(`sync-cap-${dev}`).textContent =
      `video${dev}  +${(per[dev] ?? 0).toFixed(2)} ms`;
  });
  const el = document.getElementById("multi-status");
  el.className = "status-line captured";
  el.textContent = `촬영 동기: 최대편차 ${data.stats.spread_ms.toFixed(2)} ms · σ ${data.stats.std_ms.toFixed(2)} ms`;
  document.getElementById("multi-live").disabled = false;
}

// ---- 캘리브레이션 (Mode 3) ----
let calibSub = "intrinsic";
let calibExtTimer = null;

function readBoardConfig() {
  const bt = document.getElementById("calib-board-type").value;
  const b = {
    board_type: bt,
    cols: Number(document.getElementById("calib-cols").value),
    rows: Number(document.getElementById("calib-rows").value),
    square_mm: Number(document.getElementById("calib-square").value),
  };
  if (bt === "charuco") {
    b.marker_mm = Number(document.getElementById("calib-marker").value);
    b.dictionary = document.getElementById("calib-dict").value;
  }
  return b;
}

function onBoardTypeChange() {
  const charuco = document.getElementById("calib-board-type").value === "charuco";
  document.querySelectorAll(".charuco-only").forEach((e) => (e.hidden = !charuco));
}

async function stopCalib() {
  document.getElementById("calib-int-preview").src = "";
  document.querySelectorAll("#calib-ext-grid img").forEach((i) => (i.src = ""));
  if (calibExtTimer) {
    clearInterval(calibExtTimer);
    calibExtTimer = null;
  }
  await fetch("/api/calib/reset", { method: "POST" });
}

function startCalib() {
  if (calibSub === "intrinsic") startCalibIntPreview();
  else startCalibExtPreview();
}

function setCalibSub(sub) {
  calibSub = sub;
  document.querySelectorAll(".subtab").forEach((t) =>
    t.classList.toggle("active", t.dataset.sub === sub)
  );
  document.querySelectorAll(".submode").forEach((s) =>
    s.classList.toggle("active", s.id === `calib-${sub}`)
  );
  document.getElementById("cam-pick-int").hidden = sub !== "intrinsic";
  document.getElementById("cam-pick-ext").hidden = sub !== "extrinsic";
  Promise.all([stopStreams(), stopSync(), stopCalib()]).then(startCalib);
}

// ---- Mode 4: 보정(Rectification) ----
let rectSub = "single";

function stopRectify() {
  ["rect-orig", "rect-rect"].forEach((id) => {
    const e = document.getElementById(id);
    if (e) { e.removeAttribute("src"); if (id === "rect-rect") e.hidden = true; }
  });
  const g = document.getElementById("rect-multi-grid");
  if (g) g.innerHTML = "";
  return jsonPost("/api/sync/stop", {}).catch(() => {});
}

async function startRectify() {
  await populateRectSessions();
  loadRectSingleCam();
  loadRectMultiCams();
  if (rectSub === "single") startRectSingle();
  else startRectMulti();
}

function loadRectSingleCam() {
  document.getElementById("rect-single-cam").innerHTML =
    `<option value="">카메라 선택</option>` +
    cameras.map((c) => `<option value="${c.dev}">${c.label}</option>`).join("");
}

let rectSessions = {};   // name -> devs[]
async function populateRectSessions() {
  const list = await api("/api/rectify/sessions?sub_mode=intrinsic");
  rectSessions = {};
  list.forEach((s) => (rectSessions[s.name] = s.devs));
  const opts = list.length
    ? list.map((s) => `<option value="${s.name}">${s.name} (cam ${s.devs.join(",")})</option>`).join("")
    : `<option value="">(계산 가능한 폴더 없음)</option>`;
  ["rect-session", "rect-multi-session"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = opts;
  });
}

function loadRectMultiCams() {
  document.getElementById("rect-multi-cams").innerHTML = cameras
    .map((c) => `<label><input type="checkbox" value="${c.dev}" checked> ${c.label}</label>`)
    .join("");
}

function setRectSub(sub) {
  rectSub = sub;
  document.querySelectorAll(".rsubtab").forEach((t) =>
    t.classList.toggle("active", t.dataset.rsub === sub)
  );
  document.querySelectorAll(".rsubmode").forEach((s) =>
    s.classList.toggle("active", s.id === `rectify-${sub}`)
  );
  Promise.all([stopRectify()]).then(startRectify);
}

let rectSingleStatus = {};   // 현재 선택 폴더+모델의 카메라별 상태

async function computeRectIntrinsics() {
  const session = document.getElementById("rect-session").value;
  const model = document.getElementById("rect-model").value;
  const force = document.getElementById("rect-force").checked;
  const st = document.getElementById("rect-status");
  if (!session) {
    toast("캘리브레이션 폴더(세션)를 선택하세요");
    return;
  }
  st.textContent = "계산 중… (이미지 수에 따라 수 초 걸릴 수 있습니다)";
  st.className = "status-line";
  try {
    const r = await jsonPost("/api/rectify/compute", { session, sub_mode: "intrinsic", model, force });
    if (!r.ok) {
      st.textContent = "실패: " + (r.error || "계산 실패");
      st.className = "status-line bad";
      return;
    }
    const done = Object.keys(r.cameras).map((d) => "video" + d);
    const errs = Object.entries(r.errors || {}).map(([d, m]) => `video${d}: ${m}`);
    st.textContent = `폴더 ${session} · ${model} · intrinsic: ${done.join(", ") || "없음"}`
      + (errs.length ? ` · 실패 ${errs.join("; ")}` : "");
    st.className = errs.length ? "status-line" : "status-line good";
    await refreshRectSingleStatus();     // 게이팅·품질 갱신
  } catch (e) {
    st.textContent = "오류: 계산 요청이 실패했습니다. 폴더·이미지·서버 로그를 확인하세요.";
    st.className = "status-line bad";
  }
}

function previewRectSingle() {
  const dev = document.getElementById("rect-single-cam").value;
  if (dev !== "") document.getElementById("rect-orig").src = `/api/stream/${dev}/mjpeg?t=${Date.now()}`;
  refreshRectSingleStatus();
}

function startRectSingle() {
  previewRectSingle();
}

async function refreshRectSingleStatus() {
  // 선택 카메라·폴더·모델 기준으로 토글 활성 여부·품질을 갱신(폴더가 진실의 원천).
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
  if (!ready) toggle.checked = false;
  if (hint) hint.textContent = ready ? "" :
    (dev === "" ? "카메라를 선택하세요"
     : !session ? "폴더를 선택하세요"
     : `video${dev} intrinsic 없음 — 이 폴더에서 '불러오기/계산' 필요`);
  if (ready) renderRectQuality(info, { session, dev, model });
  else renderRectQuality(null);
  updateRectSingleRight();
}

function rectAlpha() {
  return document.getElementById("rect-alpha").value;
}
function rectMultiAlpha() {
  return document.getElementById("rect-multi-alpha").value;
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
    msg.hidden = true;
    img.hidden = false;
    img.src = `/api/rectify/stream/${dev}?session=${encodeURIComponent(session)}&model=${model}&alpha=${rectAlpha()}&t=${Date.now()}`;
  } else {
    img.hidden = true;
    img.removeAttribute("src");
    msg.hidden = false;
    msg.textContent = t.disabled
      ? "이 카메라·폴더의 intrinsic이 없습니다 — 먼저 'Intrinsic 불러오기/계산'을 누르세요."
      : "보정 표시가 꺼져 있습니다";
  }
}

function rectLevelClass(level) {
  return { excellent: "q-exc", good: "q-good", fair: "q-fair", poor: "q-poor" }[level] || "";
}

function fmtK(K) {
  if (!K) return "";
  return K.map((row) => row.map((x) => Number(x).toFixed(2).padStart(9)).join(" ")).join("\n");
}

function renderRectQuality(info, ctx) {
  const el = document.getElementById("rect-quality");
  if (!info || info.has === false) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  const v = info.verdict || {};
  const errs = info.per_view_errors || [];
  const used = info.used_indices || null;   // per_view_errors[i] → 저장 프레임 정렬 위치(원본 파일 추적)
  const files = info.used_files || null;     // per_view_errors[i] → 실제 .jpg 파일 이름
  const size = info.image_size || [];
  // used_indices가 있고(재계산됨) 폴더·카메라가 특정되면 막대 클릭으로 실제 이미지를 볼 수 있다.
  const canView = !!(used && used.length === errs.length && ctx && ctx.session && ctx.dev !== "" && ctx.dev != null);
  // 라벨은 파일 이름 우선(재계산 전엔 숫자 폴백). 이미지 fetch URL은 계속 숫자 인덱스 used[i] 사용.
  const frameLabel = (i) => (files ? files[i] : (canView ? used[i] : i));
  const maxScale = Math.max(2.0, ...errs, 0.001);
  const bars = errs
    .map((e, i) => {
      const cls = e < 1.0 ? "pv-good" : e < 2.0 ? "pv-fair" : "pv-poor";
      const ht = Math.max(4, Math.round((e / maxScale) * 100));
      const clk = canView ? " pv-click" : "";
      return `<div class="pv-bar ${cls}${clk}" data-i="${i}" style="height:${ht}%" title="${frameLabel(i)}: ${e}px"></div>`;
    })
    .join("");
  let worst = "";
  if (errs.length) {
    const m = Math.max(...errs);
    worst = ` · 최악 프레임 ${frameLabel(errs.indexOf(m))} (${m.toFixed(2)}px)`;
  }
  let srcLabel = "";
  if (ctx && ctx.session) {
    const devTxt = ctx.dev != null && ctx.dev !== "" ? ` · video${ctx.dev}` : "";
    srcLabel = ` <span class="q-src">(폴더 ${ctx.session}${devTxt})</span>`;
  }
  el.hidden = false;
  el.innerHTML =
    `<div class="q-head">캘리브레이션 품질${srcLabel}</div>` +
    `<div class="q-rms ${rectLevelClass(v.level)}">재투영 오차 RMS ${Number(info.rms).toFixed(3)} px — ${v.label || ""}</div>` +
    `<div class="q-note">추정한 K·왜곡으로 체커보드 코너를 다시 투영했을 때 실제 검출 위치와의 평균 오차입니다. <b>낮을수록 정확</b> (보통 &lt;1px 양호).</div>` +
    `<div class="q-meta">사용 이미지 ${info.n_images || errs.length}장 · ${info.model} · ${size[0]}×${size[1]}${worst}</div>` +
    `<div class="pv-bars">${bars}</div>` +
    `<div class="q-note">↑ 막대 = 프레임별 재투영 오차. 유독 높은 막대(빨강)는 흔들림/검출 오류일 수 있어, 그 이미지를 빼고 다시 촬영·계산하면 개선될 수 있습니다.` +
    (canView
      ? ` <b>막대를 클릭</b>하면 해당 촬영 이미지를 아래에서 확인할 수 있습니다.`
      : ` <i>('재계산'을 한 번 실행하면 막대 클릭으로 원본 이미지를 확인할 수 있습니다.)</i>`) +
    `</div>` +
    (canView
      ? `<div class="q-view" id="rect-q-view" hidden><button type="button" class="q-view-close" id="rect-q-view-close">✕ 닫기</button><img id="rect-q-view-img" alt="선택 프레임"><div class="q-view-cap" id="rect-q-view-cap"></div></div>`
      : ``) +
    `<details class="q-detail"><summary>K·왜곡계수 보기</summary><pre>${fmtK(info.K)}\n\ndist: ${JSON.stringify(info.dist)}</pre></details>` +
    `<details class="q-help"><summary>이 수치는 무엇인가요?</summary><ul>` +
    `<li><b>재투영 오차(RMS)</b>: 캘리브레이션 정확도. 낮을수록 좋음. 매우 좋음&lt;0.5 / 양호&lt;1 / 보통&lt;2 / 미흡≥2 px.</li>` +
    `<li><b>프레임별 오차</b>: 각 촬영 장면의 오차. 특정 이미지만 크면 그 장면 품질이 낮은 것.</li>` +
    `<li><b>K(내부 행렬)</b>: fx·fy = 초점거리(px), cx·cy = 주점(광학 중심 좌표).</li>` +
    `<li><b>dist(왜곡계수)</b>: 렌즈 왜곡. pinhole=k1,k2,p1,p2,k3 / fisheye=k1~k4.</li>` +
    `</ul></details>`;
  if (canView) {
    const view = document.getElementById("rect-q-view");
    const collapse = () => {
      view.hidden = true;
      el.querySelectorAll(".pv-bar").forEach((b) => b.classList.remove("pv-sel"));
    };
    const closeBtn = document.getElementById("rect-q-view-close");
    if (closeBtn) closeBtn.addEventListener("click", collapse);
    el.querySelectorAll(".pv-bar.pv-click").forEach((bar) => {
      bar.addEventListener("click", () => {
        // 이미 선택된 막대를 다시 클릭하면 접기(토글)
        if (bar.classList.contains("pv-sel")) {
          collapse();
          return;
        }
        const i = Number(bar.dataset.i);
        const fno = used[i];
        document.getElementById("rect-q-view-img").src =
          `/api/calib/frame/intrinsic/${encodeURIComponent(ctx.session)}/${ctx.dev}/${fno}?t=${Date.now()}`;
        document.getElementById("rect-q-view-cap").textContent =
          `${frameLabel(i)} · 재투영 오차 ${errs[i]}px`;
        view.hidden = false;
        el.querySelectorAll(".pv-bar").forEach((b) => b.classList.remove("pv-sel"));
        bar.classList.add("pv-sel");
      });
    });
  }
}


function selectedRectMultiDevs() {
  return [...document.querySelectorAll("#rect-multi-cams input:checked")].map((c) => Number(c.value));
}

let rectMultiInfo = {};

function rectMultiOn() {
  return document.getElementById("rect-multi-toggle").checked;
}
function rectMultiModel() {
  return document.getElementById("rect-multi-model").value;
}
function rectMultiSession() {
  return document.getElementById("rect-multi-session").value;
}

async function startRectMulti() {
  const devs = selectedRectMultiDevs();
  if (!devs.length) return;
  await jsonPost("/api/sync/start", { devices: devs, sync_mode: 1 });
  await jsonPost("/api/rectify/multi_toggle", { on: rectMultiOn() });
  await buildRectMultiGrid(devs);
}

async function buildRectMultiGrid(devs) {
  // 선택 폴더+모델의 카메라별 상태를 한 번 조회해 캐시. 스트림은 카메라당 하나(연결 1개) —
  // 폴더·모델을 URL에 실어 서버가 판단하며, 토글해도 재생성하지 않는다.
  const session = rectMultiSession(), model = rectMultiModel();
  rectMultiInfo = session
    ? (await api(`/api/rectify/session_status?session=${encodeURIComponent(session)}&model=${model}`)).cameras
    : {};
  const t = Date.now();
  const q = session
    ? `?session=${encodeURIComponent(session)}&model=${model}&alpha=${rectMultiAlpha()}&t=${t}`
    : `?t=${t}`;
  document.getElementById("rect-multi-grid").innerHTML = devs
    .map(
      (d) =>
        `<figure><img id="rect-m-${d}" src="/api/rectify/sync/stream/${d}${q}">` +
        `<figcaption id="rect-m-cap-${d}"></figcaption></figure>`
    )
    .join("");
  updateRectMultiCaptions(devs);
  gateRectMultiToggle(devs);
}

function gateRectMultiToggle(devs) {
  const any = devs.some((d) => rectMultiInfo[String(d)] && rectMultiInfo[String(d)].has);
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

function renderVerdict(el, verdict, diversity) {
  el.hidden = false;
  el.className = "verdict " + (verdict.ok ? "pass" : "fail");
  let html = verdict.ok ? "✅ 검증 통과 — 저장 가능" : "❌ 검증 실패 — 다시 촬영하세요";
  if (verdict.reasons && verdict.reasons.length)
    html += "<ul>" + verdict.reasons.map((r) => `<li>${r}</li>`).join("") + "</ul>";
  if (diversity && diversity.suggestion)
    html += `<div class="coverage missing">${diversity.suggestion}</div>`;
  el.innerHTML = html;
}

// 세션 활성 상태에 따른 버튼 enable/disable (sub = "int" | "ext")
const calibActive = { int: false, ext: false };
function setCalibActive(sub, active) {
  calibActive[sub] = active;
  document.getElementById(`calib-${sub}-start`).disabled = active;
  document.getElementById(`calib-${sub}-end`).disabled = !active;
  document.getElementById(`calib-${sub}-capture`).disabled = !active;
  document.getElementById(`calib-${sub}-save`).disabled = true;
  const sel = document.getElementById(`calib-${sub}-sessions`);
  sel.disabled = active;   // 세션 중에는 이어하기 드롭다운도 잠금
  document.getElementById(`calib-${sub}-resume`).disabled = active || !sel.options.length;
  // 세션 중에는 세션을 정의하는 옵션(보드 설정·카메라·링)을 잠근다 → 종료 시 해제.
  ["calib-board-type", "calib-cols", "calib-rows", "calib-square", "calib-marker",
   "calib-dict", "calib-int-cam", "calib-ext-ring"].forEach((id) => {
    document.getElementById(id).disabled = active;
  });
  document.querySelectorAll("#calib-ext-cams input").forEach((c) => (c.disabled = active));
}

function setBoardForm(board) {
  document.getElementById("calib-board-type").value = board.board_type;
  document.getElementById("calib-cols").value = board.cols;
  document.getElementById("calib-rows").value = board.rows;
  document.getElementById("calib-square").value = board.square_mm;
  if (board.board_type === "charuco") {
    document.getElementById("calib-marker").value = board.marker_mm;
    document.getElementById("calib-dict").value = board.dictionary;
  }
  onBoardTypeChange();
}

function populateCalibSessions(sub) {
  const subMode = sub === "int" ? "intrinsic" : "extrinsic";
  return api(`/api/calib/sessions?sub_mode=${subMode}`).then((list) => {
    const sel = document.getElementById(`calib-${sub}-sessions`);
    sel.innerHTML = list
      .map((s) => `<option value="${s.name}">${s.name} · ${s.count}장</option>`)
      .join("");
    document.getElementById(`calib-${sub}-resume`).disabled =
      calibActive[sub] || !list.length;
  });
}

// --- Intrinsic ---
async function startCalibIntPreview() {
  const dev = document.getElementById("calib-int-cam").value;
  if (!dev) return;
  document.getElementById("calib-int-still").hidden = true;
  const img = document.getElementById("calib-int-preview");
  img.hidden = false;
  img.src = `/api/stream/${dev}/mjpeg?t=${Date.now()}`;
  document.getElementById("calib-int-verdict").hidden = true;
  await populateCalibSessions("int");
  setCalibActive("int", false);
}

async function calibIntStart() {
  const dev = document.getElementById("calib-int-cam").value;
  if (!dev) {
    toast("카메라를 선택하세요");
    return;
  }
  const r = await jsonPost("/api/calib/start", {
    sub_mode: "intrinsic",
    board: readBoardConfig(),
    devices: [Number(dev)],
  });
  if (!r.ok) {
    toast(r.error || "세션 시작 실패");
    return;
  }
  setCalibActive("int", true);
  document.getElementById("calib-int-verdict").hidden = true;
  renderCalibIntStatus(r.counts, null);
  toast("세션 시작됨");
}

async function calibIntEnd() {
  await fetch("/api/calib/reset", { method: "POST" });
  document.getElementById("calib-int-verdict").hidden = true;
  document.getElementById("calib-int-coverage").innerHTML = "";
  const st = document.getElementById("calib-int-status");
  st.className = "status-line";
  st.textContent = "세션을 시작하세요.";
  startCalibIntPreview(); // 프리뷰 재개 + 비활성 상태 + 세션 목록 갱신
  toast("세션 종료됨");
}

async function calibIntResume() {
  const sel = document.getElementById("calib-int-sessions");
  if (!sel.value) return;
  const dev = document.getElementById("calib-int-cam").value;
  const r = await jsonPost("/api/calib/resume", {
    sub_mode: "intrinsic",
    name: sel.value,
    devices: dev ? [Number(dev)] : [],
  });
  if (!r.ok) {
    toast(r.error || "이어하기 실패");
    return;
  }
  setBoardForm(r.board); // 폼을 불러온 세션의 보드 설정으로 맞춘 뒤 잠금
  if (r.devices && r.devices.length) {
    document.getElementById("calib-int-cam").value = r.devices[0];
    document.getElementById("calib-int-still").hidden = true;
    const img = document.getElementById("calib-int-preview");
    img.hidden = false;
    img.src = `/api/stream/${r.devices[0]}/mjpeg?t=${Date.now()}`;
  }
  setCalibActive("int", true);
  document.getElementById("calib-int-verdict").hidden = true;
  renderCalibIntStatus(r.counts, r.coverage);
  toast(`이어하기: ${r.resumed}`);
}

async function calibIntCapture() {
  toast("촬영·검증 중...");
  let d;
  try {
    d = await jsonPost("/api/calib/capture", {});
  } catch (e) {
    toast("촬영 실패");
    return;
  }
  if (!d.ok) {
    toast(d.error || "촬영 실패");
    return;
  }
  const dev = document.getElementById("calib-int-cam").value;
  const still = document.getElementById("calib-int-still");
  still.src = d.overlay[dev];
  still.hidden = false;
  document.getElementById("calib-int-preview").hidden = true;
  renderVerdict(document.getElementById("calib-int-verdict"), d.verdict, d.diversity);
  document.getElementById("calib-int-save").disabled = !d.verdict.ok;
}

async function calibIntSave() {
  const r = await jsonPost("/api/calib/accept", {});
  if (!r.ok) {
    toast(r.error || "저장 실패");
    return;
  }
  renderCalibIntStatus(r.counts, r.coverage);
  document.getElementById("calib-int-save").disabled = true;
  document.getElementById("calib-int-verdict").hidden = true;
  const dev = document.getElementById("calib-int-cam").value;
  document.getElementById("calib-int-still").hidden = true;
  const img = document.getElementById("calib-int-preview");
  img.hidden = false;
  img.src = `/api/stream/${dev}/mjpeg?t=${Date.now()}`;
  toast(`저장됨 (${r.counts[dev] ?? 0}장)`);
}

function renderCalibIntStatus(counts, coverage) {
  const dev = document.getElementById("calib-int-cam").value;
  const n = counts ? counts[dev] ?? 0 : 0;
  const el = document.getElementById("calib-int-status");
  let txt = `수집: ${n}장`;
  if (coverage) txt += ` · 커버리지 ${coverage.filled}/${coverage.total}`;
  el.className = "status-line" + (n > 0 ? " captured" : "");
  el.textContent = txt;
  const cov = document.getElementById("calib-int-coverage");
  if (coverage && coverage.suggestions && coverage.suggestions.length) {
    cov.innerHTML =
      "권장 미커버 구도: " +
      coverage.suggestions.map((s) => `<span class="missing">${s}</span>`).join(", ");
  } else {
    cov.innerHTML = "";
  }
}

// --- Extrinsic ---
const EXT_PAIR_TARGET = 6; // 인접 쌍별 권장 최소 shot 수

function selectedCalibExtDevs() {
  return [...document.querySelectorAll("#calib-ext-cams input:checked")].map((c) => c.value);
}

async function startCalibExtPreview(activate = false) {
  const devs = selectedCalibExtDevs();
  const grid = document.getElementById("calib-ext-grid");
  if (!devs.length) {
    grid.innerHTML = "";
    document.getElementById("calib-ext-status").textContent = "카메라를 선택하세요.";
    await populateCalibSessions("ext");
    setCalibActive("ext", activate);
    return;
  }
  await jsonPost("/api/sync/start", { devices: devs, sync_mode: 1 });
  grid.innerHTML = devs
    .map(
      (d) =>
        `<figure><img id="calib-ext-img-${d}" src="/api/sync/stream/${d}?t=${Date.now()}">` +
        `<figcaption id="calib-ext-cap-${d}">video${d}</figcaption></figure>`
    )
    .join("");
  document.getElementById("calib-ext-verdict").hidden = true;
  if (calibExtTimer) clearInterval(calibExtTimer);
  calibExtTimer = setInterval(pollCalibExtSync, 700);
  // 세션 목록 populate를 await한 뒤 활성 상태를 확정한다(resume에서 버튼이 다시 꺼지는 race 방지).
  await populateCalibSessions("ext");
  setCalibActive("ext", activate);
}

async function pollCalibExtSync() {
  const s = await api("/api/sync/status");
  const el = document.getElementById("calib-ext-status");
  if (!s || !s.ready) {
    el.className = "status-line";
    el.textContent = "동기화 측정 준비 중…";
    return;
  }
  const lvl = s.spread_ms < 2 ? "good" : s.spread_ms < 10 ? "warn" : "bad";
  const dot = { good: "🟢", warn: "🟡", bad: "🔴" }[lvl];
  el.className = "status-line " + lvl;
  el.textContent = `${dot} 동기 최대편차 ${s.spread_ms.toFixed(2)} ms · σ ${s.std_ms.toFixed(2)} ms`;
}

function renderPairCoverage(pairs) {
  const el = document.getElementById("calib-ext-pairs");
  if (!pairs || !pairs.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML =
    `쌍 커버리지 (목표 ${EXT_PAIR_TARGET}장): ` +
    pairs
      .map((p) => {
        const cls = p.count < EXT_PAIR_TARGET ? "missing" : "";
        return `<span class="${cls}">${p.pair}(${p.count})</span>`;
      })
      .join("  ");
}

async function calibExtStart() {
  const devs = selectedCalibExtDevs();
  if (devs.length < 2) {
    toast("2대 이상 선택하세요");
    return;
  }
  const r = await jsonPost("/api/calib/start", {
    sub_mode: "extrinsic",
    board: readBoardConfig(),
    devices: devs.map(Number),
    ring: document.getElementById("calib-ext-ring").checked,
  });
  if (!r.ok) {
    toast(r.error || "세션 시작 실패");
    return;
  }
  setCalibActive("ext", true);
  document.getElementById("calib-ext-verdict").hidden = true;
  renderPairCoverage(r.pairs);
  toast("세션 시작됨");
}

async function calibExtEnd() {
  await fetch("/api/calib/reset", { method: "POST" });
  document.getElementById("calib-ext-verdict").hidden = true;
  document.getElementById("calib-ext-pairs").innerHTML = "";
  startCalibExtPreview(); // 프리뷰 재개 + 비활성 상태 + 세션 목록 갱신
  toast("세션 종료됨");
}

async function calibExtResume() {
  const sel = document.getElementById("calib-ext-sessions");
  if (!sel.value) return;
  const r = await jsonPost("/api/calib/resume", {
    sub_mode: "extrinsic",
    name: sel.value,
    devices: selectedCalibExtDevs().map(Number),
    ring: document.getElementById("calib-ext-ring").checked,
  });
  if (!r.ok) {
    toast(r.error || "이어하기 실패");
    return;
  }
  setBoardForm(r.board); // 폼을 불러온 세션의 보드 설정으로 맞춘 뒤 잠금
  if (r.devices && r.devices.length) {
    document.querySelectorAll("#calib-ext-cams input").forEach((c) => {
      c.checked = r.devices.includes(Number(c.value));
    });
    await stopSync();
    await startCalibExtPreview(true); // 재개된 카메라로 동기 프리뷰 시작 + 활성 상태로 확정
  } else {
    setCalibActive("ext", true);
  }
  document.getElementById("calib-ext-verdict").hidden = true;
  renderPairCoverage(r.pairs);
  toast(`이어하기: ${r.resumed} (shot ${r.counts.shots}개)`);
}

async function calibExtCapture() {
  toast("동기 촬영·검증 중...");
  let d;
  try {
    d = await jsonPost("/api/calib/capture", {});
  } catch (e) {
    toast("촬영 실패");
    return;
  }
  if (!d.ok) {
    toast(d.error || "촬영 실패");
    return;
  }
  if (calibExtTimer) {
    clearInterval(calibExtTimer); // 그리드 고정(freeze)
    calibExtTimer = null;
  }
  Object.entries(d.overlay).forEach(([dev, uri]) => {
    const img = document.getElementById(`calib-ext-img-${dev}`);
    if (img) img.src = uri;
    const cap = document.getElementById(`calib-ext-cap-${dev}`);
    if (cap) {
      const pc = d.verdict.per_cam && d.verdict.per_cam[dev];
      const usable = pc && pc.ok;
      const detected = d.metrics[dev] && d.metrics[dev].detected;
      // ✓사용가능(저장됨) / △검출됐지만 품질 미달(제외) / ✗미검출(제외)
      cap.textContent = usable
        ? `video${dev} ✓사용가능`
        : `video${dev} ${detected ? "△품질미달·제외" : "✗미검출·제외"}`;
    }
  });
  const el = document.getElementById("calib-ext-verdict");
  el.hidden = false;
  el.className = "verdict " + (d.verdict.ok ? "pass" : "fail");
  let html = d.verdict.ok
    ? `✅ 저장 가능 — 동시 검출 쌍: ${d.covered_pairs.join(", ")}`
    : "❌ 저장 불가 — 인접 쌍이 동시에 선명히 검출되지 않았습니다";
  if (d.verdict.reasons && d.verdict.reasons.length)
    html += "<ul>" + d.verdict.reasons.map((r) => `<li>${r}</li>`).join("") + "</ul>";
  html += `<div class="coverage">동기 최대편차 ${d.sync_stats.spread_ms.toFixed(2)} ms · σ ${d.sync_stats.std_ms.toFixed(2)} ms</div>`;
  el.innerHTML = html;
  document.getElementById("calib-ext-save").disabled = !d.verdict.ok;
}

async function calibExtSave() {
  const r = await jsonPost("/api/calib/accept", {});
  if (!r.ok) {
    toast(r.error || "저장 실패");
    return;
  }
  renderPairCoverage(r.pairs);
  document.getElementById("calib-ext-save").disabled = true;
  document.getElementById("calib-ext-verdict").hidden = true;
  selectedCalibExtDevs().forEach((d) => {
    const img = document.getElementById(`calib-ext-img-${d}`);
    if (img) img.src = `/api/sync/stream/${d}?t=${Date.now()}`;
    const cap = document.getElementById(`calib-ext-cap-${d}`);
    if (cap) cap.textContent = `video${d}`;
  });
  if (!calibExtTimer) calibExtTimer = setInterval(pollCalibExtSync, 700);
  toast(`shot 저장됨 (총 ${r.counts.shots}개)`);
}

document.querySelectorAll(".subtab").forEach((t) =>
  t.addEventListener("click", () => setCalibSub(t.dataset.sub))
);
document.getElementById("calib-board-type").addEventListener("change", onBoardTypeChange);
document.getElementById("calib-int-cam").addEventListener("change", () => {
  if (activeMode() === "calib" && calibSub === "intrinsic") startCalibIntPreview();
});
document.getElementById("calib-int-start").addEventListener("click", calibIntStart);
document.getElementById("calib-int-end").addEventListener("click", calibIntEnd);
document.getElementById("calib-int-resume").addEventListener("click", calibIntResume);
document.getElementById("calib-int-capture").addEventListener("click", calibIntCapture);
document.getElementById("calib-int-save").addEventListener("click", calibIntSave);
document.getElementById("calib-ext-start").addEventListener("click", calibExtStart);
document.getElementById("calib-ext-end").addEventListener("click", calibExtEnd);
document.getElementById("calib-ext-resume").addEventListener("click", calibExtResume);
document.getElementById("calib-ext-capture").addEventListener("click", calibExtCapture);
document.getElementById("calib-ext-save").addEventListener("click", calibExtSave);
document.getElementById("calib-ext-cams").addEventListener("change", () => {
  if (activeMode() === "calib" && calibSub === "extrinsic")
    stopSync().then(startCalibExtPreview);
});

document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => setMode(t.dataset.mode))
);
document.querySelectorAll(".rsubtab").forEach((t) =>
  t.addEventListener("click", () => setRectSub(t.dataset.rsub))
);
document.getElementById("rect-compute").addEventListener("click", computeRectIntrinsics);
document.getElementById("rect-single-cam").addEventListener("change", () => {
  if (activeMode() === "rectify" && rectSub === "single") previewRectSingle();
});
document.getElementById("rect-session").addEventListener("change", () => {
  if (activeMode() === "rectify" && rectSub === "single") refreshRectSingleStatus();
});
document.getElementById("rect-model").addEventListener("change", () => {
  if (activeMode() === "rectify" && rectSub === "single") refreshRectSingleStatus();
});
document.getElementById("rect-toggle").addEventListener("change", updateRectSingleRight);
document.getElementById("rect-alpha").addEventListener("input", () => {
  document.getElementById("rect-alpha-val").textContent = Number(rectAlpha()).toFixed(1);
});
document.getElementById("rect-alpha").addEventListener("change", updateRectSingleRight);
document.getElementById("rect-multi-alpha").addEventListener("input", () => {
  document.getElementById("rect-multi-alpha-val").textContent = Number(rectMultiAlpha()).toFixed(1);
});
document.getElementById("rect-multi-alpha").addEventListener("change", () => {
  if (activeMode() === "rectify" && rectSub === "multi") stopSync().then(startRectMulti);
});
document.getElementById("rect-multi-start").addEventListener("click", startRectMulti);
document.getElementById("rect-multi-cams").addEventListener("change", () => {
  if (activeMode() === "rectify" && rectSub === "multi") stopSync().then(startRectMulti);
});
document.getElementById("rect-multi-session").addEventListener("change", () => {
  if (activeMode() === "rectify" && rectSub === "multi") stopSync().then(startRectMulti);
});
document.getElementById("rect-multi-model").addEventListener("change", () => {
  if (activeMode() === "rectify" && rectSub === "multi") stopSync().then(startRectMulti);
});
document.getElementById("rect-multi-toggle").addEventListener("change", async () => {
  await jsonPost("/api/rectify/multi_toggle", { on: rectMultiOn() });
  updateRectMultiCaptions(selectedRectMultiDevs());   // 연결 재생성 없이 서버에서 내용만 전환
});
document
  .getElementById("single-cam")
  .addEventListener("change", startSinglePreview);
document
  .getElementById("single-capture")
  .addEventListener("click", singleCapture);
document.getElementById("single-save").addEventListener("click", save);
document.getElementById("single-live").addEventListener("click", () => {
  if (activeMode() === "single") startSinglePreview();
});
document.getElementById("multi-capture").addEventListener("click", multiCapture);
document.getElementById("multi-save").addEventListener("click", save);
document.getElementById("multi-live").addEventListener("click", () => {
  if (activeMode() === "multi") startSyncSession();
});
document.getElementById("multi-cams").addEventListener("change", () => {
  if (activeMode() === "multi") stopSync().then(startSyncSession);
});
document.getElementById("resolution").addEventListener("change", applyResolution);
document.getElementById("refresh").addEventListener("click", async () => {
  await fetch("/api/cameras/refresh", { method: "POST" });
  await loadCameras();
  await loadResolutions();  // 카메라가 바뀌면 지원 해상도 목록도 갱신
  setMode(activeMode());  // 재감지 후 현재 모드 프리뷰 재시작
  toast("재감지 완료");
});
document.getElementById("shutdown").addEventListener("click", async () => {
  if (!confirm("프로그램을 종료하시겠습니까? 종료 후에는 터미널에서 다시 실행해야 합니다.")) {
    return;
  }
  document.getElementById("single-preview").src = "";  // 프리뷰 스트림 중단
  try {
    // 서버가 응답 직후 종료되므로 연결이 끊길 수 있다 — 실패해도 정상으로 본다.
    await fetch("/api/shutdown", { method: "POST" });
  } catch (e) {
    /* 종료 중 연결 끊김 — 예상된 동작 */
  }
  document.getElementById("shutdown-overlay").hidden = false;
});

onBoardTypeChange(); // 초기 보드 종류에 맞춰 옵션 표시/숨김 + 힌트
loadCameras().then(loadResolutions).then(() => setMode("single"));
