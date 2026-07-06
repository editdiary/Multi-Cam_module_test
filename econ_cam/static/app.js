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

async function stopStreams() {
  document.getElementById("single-preview").src = "";
  await fetch("/api/stream/stop", { method: "POST" });
}

function setMode(mode) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.mode === mode)
  );
  document.querySelectorAll(".mode").forEach((s) =>
    s.classList.toggle("active", s.id === mode)
  );
  stopStreams().then(() => {
    if (mode === "single") startSinglePreview();
  });
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

async function multiCapture() {
  const devs = [...document.querySelectorAll("#multi-cams input:checked")].map(
    (c) => c.value
  );
  if (!devs.length) {
    toast("카메라를 선택하세요");
    return;
  }
  toast("동기 촬영 중...");
  let data;
  try {
    data = await jsonPost("/api/capture", {
      mode: "multi",
      devices: devs,
      sync_mode: 1,
    });
  } catch (e) {
    toast("동기 촬영 실패");
    return;
  }
  if (!data.images) {
    toast("동기 촬영 실패");
    return;
  }
  document.getElementById("multi-grid").innerHTML = Object.entries(data.images)
    .map(
      ([dev, uri]) =>
        `<figure><img src="${uri}"><figcaption>video${dev}</figcaption></figure>`
    )
    .join("");
  const s = data.stats;
  const rows = Object.entries(s.per_camera)
    .map(
      ([dev, ms]) => `<tr><td>video${dev}</td><td>${ms.toFixed(3)} ms</td></tr>`
    )
    .join("");
  document.getElementById("sync-stats").innerHTML =
    `<tr><th>카메라</th><th>상대 타임스탬프</th></tr>${rows}` +
    `<tr class="summary"><td>최대 편차 (max−min)</td><td>${s.spread_ms.toFixed(
      3
    )} ms</td></tr>` +
    `<tr class="summary"><td>표준편차</td><td>${s.std_ms.toFixed(3)} ms</td></tr>`;
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
document.getElementById("refresh").addEventListener("click", async () => {
  await fetch("/api/cameras/refresh", { method: "POST" });
  await loadCameras();
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

loadCameras().then(() => setMode("single"));
