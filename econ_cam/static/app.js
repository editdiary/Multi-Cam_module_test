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
  Promise.all([stopStreams(), stopSync(), stopCalib()]).then(() => {
    if (mode === "single") startSinglePreview();
    if (mode === "multi") startSyncSession();
    if (mode === "calib") startCalib();
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
function startCalibIntPreview() {
  const dev = document.getElementById("calib-int-cam").value;
  if (!dev) return;
  document.getElementById("calib-int-still").hidden = true;
  const img = document.getElementById("calib-int-preview");
  img.hidden = false;
  img.src = `/api/stream/${dev}/mjpeg?t=${Date.now()}`;
  document.getElementById("calib-int-verdict").hidden = true;
  populateCalibSessions("int").then(() => setCalibActive("int", false));
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

async function startCalibExtPreview() {
  const devs = selectedCalibExtDevs();
  const grid = document.getElementById("calib-ext-grid");
  if (!devs.length) {
    grid.innerHTML = "";
    document.getElementById("calib-ext-status").textContent = "카메라를 선택하세요.";
    populateCalibSessions("ext").then(() => setCalibActive("ext", false));
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
  populateCalibSessions("ext").then(() => setCalibActive("ext", false));
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
    await startCalibExtPreview(); // 재개된 카메라로 동기 프리뷰 시작 (비활성 상태로 둠)
  }
  setCalibActive("ext", true);
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
