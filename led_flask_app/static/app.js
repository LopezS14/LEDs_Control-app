// ======================
// Helpers HTTP
// ======================
async function getJSON(url) {
  const r = await fetch(url);
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "Error");
  return data;
}

async function postJSON(url, payload) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {})
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "Error");
  return data;
}

// ======================
// Getters UI
// ======================
function getMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function getIntensity() {
  // Tu slider real es intSlider (no "intensity")
  return parseInt(document.getElementById("intSlider").value, 10);
}

// ======================
// Elements
// ======================
const statusEl = document.getElementById("status");
const captureInfo = document.getElementById("captureInfo");
const portSelect = document.getElementById("portSelect");
const video = document.getElementById("video");
const btnToggle = document.getElementById("btnToggle");

let isConnected = false;

// ======================
// Serial ports
// ======================
async function refreshPorts() {
  const d = await getJSON("/api/serial/ports");
  const ports = d.ports || [];

  portSelect.innerHTML = `<option value="">Auto (primer puerto)</option>`;
  for (const p of ports) {
    const opt = document.createElement("option");
    opt.value = p.device;
    opt.textContent = `${p.device} — ${p.description}`;
    portSelect.appendChild(opt);
  }
}

document.getElementById("btnRefreshPorts").onclick = () => {
  refreshPorts().catch(e => alert(e.message));
};

// ======================
// Connect / Disconnect toggle
// ======================
btnToggle.onclick = async () => {
  try {
    if (!isConnected) {
      const port = portSelect.value || null;
      const d = await postJSON("/api/serial/connect", port ? { port } : {});

      statusEl.innerHTML = `<i class="bi bi-check-circle-fill"></i> Conectado (${d.port})`;
      statusEl.classList.remove("desconectado");
      statusEl.classList.add("conectado");

      btnToggle.textContent = "Desconectar";
      btnToggle.classList.add("desconectar");
      isConnected = true;
    } else {
      await postJSON("/api/serial/disconnect", {});

      statusEl.innerHTML = `<i class="bi bi-x-octagon-fill"></i> Desconectado`;
      statusEl.classList.remove("conectado");
      statusEl.classList.add("desconectado");

      btnToggle.textContent = "Conectar";
      btnToggle.classList.remove("desconectar");
      isConnected = false;
    }
  } catch (e) {
    alert(e.message);
  }
};

// ======================
// LED mode
// ======================
document.getElementById("btnApplyMode").onclick = async () => {
  try {
    const mode = getMode();
    const d = await postJSON("/api/led/mode", { mode });

    // backend solo regresa cmd, así que mostramos mode local
    statusEl.textContent = `LED aplicado: ${mode} (cmd=${d.cmd})`;
  } catch (e) {
    alert(e.message);
  }
};

// ======================
// Intensity slider UI + apply
// ======================
document.addEventListener("DOMContentLoaded", () => {
  const slider = document.getElementById("intSlider");
  const valueLabel = document.getElementById("intValue");

  valueLabel.textContent = slider.value;
  slider.addEventListener("input", () => {
    valueLabel.textContent = slider.value;
  });
});

document.getElementById("btnApplyIntensity").onclick = async () => {
  try {
    const level = getIntensity();
    const d = await postJSON("/api/led/intensity", { level });

    // backend solo regresa cmd, así que mostramos level local
    statusEl.textContent = `Intensidad aplicada: ${level} (cmd=${d.cmd})`;
  } catch (e) {
    alert(e.message);
  }
};

// ======================
// Camera start/stop + stream refresh
// ======================
function restartStream() {
  video.src = `/video_feed?t=${Date.now()}`;
}

document.getElementById("btnCamStart").onclick = async () => {
  try {
    const index = parseInt(document.getElementById("camIndex").value, 10);
    await postJSON("/api/camera/start", { index });

    statusEl.textContent = `Vista iniciada en cámara ${index}`;
    restartStream();
  } catch (e) {
    alert(e.message);
  }
};

document.getElementById("btnCamStop").onclick = async () => {
  try {
    await postJSON("/api/camera/stop", {});
    statusEl.textContent = "Cámara detenida";
  } catch (e) {
    alert(e.message);
  }
};

// ======================
// Capture series (FIX real)
// ======================
async function captureSeries() {
  const n_images = parseInt(document.getElementById("nImages").value, 10);
  const folder = (document.getElementById("folderName").value || "").trim() || "Sesion_01";
  const mode = getMode();
  const intensity = getIntensity();

  captureInfo.textContent = "Capturando...";
  const d = await postJSON("/api/capture/series", {
    n_images,
    folder,
    mode,
    intensity
  });

  captureInfo.textContent = `OK: ${d.n_images} imgs → ${d.path}`;
  return d;
}

document.getElementById("btnCapture").onclick = async () => {
  try {
    await captureSeries();
  } catch (e) {
    captureInfo.textContent = `Error: ${e.message}`;
    alert(e.message);
  }
};

// ======================
// Zoom visual (CSS transform)
// ======================
let zoom = 1.0;
const zoomVal = document.getElementById("zoomVal");

function setZoom(z) {
  zoom = Math.max(0.25, Math.min(5.0, z));
  video.style.transform = `scale(${zoom})`;
  zoomVal.textContent = `${zoom.toFixed(2)}x`;
}

document.getElementById("zoomIn").onclick = () => setZoom(zoom + 0.25);
document.getElementById("zoomOut").onclick = () => setZoom(zoom - 0.25);
document.getElementById("zoomReset").onclick = () => setZoom(1.0);

// ======================
// Init
// ======================
setZoom(1.0);
refreshPorts().catch(() => {});
restartStream();
