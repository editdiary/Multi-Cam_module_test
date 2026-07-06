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
  Promise.all([stopStreams(), stopSync()]).then(() => {
    if (mode === "single") startSinglePreview();
    if (mode === "multi") startSyncSession();
  });
}

function activeMode() {
  return document.querySelector(".tab.active").dataset.mode;
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

loadCameras().then(loadResolutions).then(() => setMode("single"));
