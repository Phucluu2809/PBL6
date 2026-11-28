"use strict";

const state = { snapshot: null, messageAfter: 0, renderedJobs: new Set(), trials: [], connected: false, pendingSavedTrial: null, savedTrial: null, sessionRequestPending: false };
let identityRequest = 0;
let identityJob;
let coffeeBusy = false;
const coffeeModels = [
  {id: "logistic", name: "Logistic Regression"},
  {id: "random_forest", name: "Random Forest"},
  {id: "svm", name: "SVM (RBF)"}
];
let autoPredictedTrial;
let comparisonJob;
let comparisonBusy = false;
let defaultModel = {};
let trialCatalogJson;
const selectionKey = "robonose.comparison-selection.v1";
let savedSelection = readComparisonSelection();
let draftSelection = new Set(savedSelection);
const titles = {
  realtime: "Tín hiệu realtime",
  control: "Điều khiển thu mẫu",
  identity: "Dự đoán danh tính",
  comparison: "Đối sánh",
  library: "Danh sách mẫu",
  coffee: "Phát hiện cà phê"
};
const phases = ["MONITOR", "BASELINE", "WAIT_EXPOSURE", "EXPOSURE", "WAIT_RECOVERY", "RECOVERY", "WAIT_FINISH", "WAIT_NAME", "MONITOR_NEXT"];
const chartColors = ["#46d2bb", "#73a9ff", "#f4a261", "#bd93f9", "#62d69b", "#f07178", "#56c6e1", "#d9c678"];

function byId(id) { return document.getElementById(id); }
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}
function formatNumber(value, digits = 2) {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? "—" : Number(value).toFixed(digits);
}
function formatAddress(value, fallback) {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "number") return `0x${value.toString(16).toUpperCase()}`;
  return String(value);
}
function requestId() {
  return globalThis.crypto?.randomUUID?.() || `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
async function api(path, options = {}) {
  const response = await fetch(path, {headers: {"Content-Type": "application/json"}, cache: "no-store", ...options});
  let body;
  try { body = await response.json(); } catch { body = {error: `HTTP ${response.status}`}; }
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}

function setConnection(online, message = "") {
  state.connected = online;
  const dot = byId("sidebar-dot");
  dot.classList.toggle("online", online);
  dot.classList.toggle("error", !online);
  byId("sidebar-status").textContent = online ? "Đã kết nối web" : "Mất kết nối web";
  const alert = byId("global-alert");
  alert.hidden = online;
  alert.textContent = online ? "" : (message || "Không nhận được snapshot từ backend.");
}

function initNavigation() {
  document.querySelectorAll(".nav-item").forEach(button => {
    button.addEventListener("click", () => {
      const page = button.dataset.page;
      document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item === button));
      document.querySelectorAll(".page").forEach(section => {
        const active = section.id === `page-${page}`;
        section.classList.toggle("active", active);
        section.hidden = !active;
      });
      byId("page-title").textContent = titles[page];
      const contained = page === "library" || page === "comparison";
      document.querySelector(".shell").classList.toggle("contained-page", contained);
      if (contained) window.scrollTo(0, 0);
      if (state.snapshot) requestAnimationFrame(() => drawCharts(state.snapshot));
    });
  });
}

function renderWarnings(snapshot) {
  byId("warning-count").textContent = String(snapshot.warnings.length);
  const list = byId("warning-list");
  if (!snapshot.warnings.length) {
    list.innerHTML = '<div class="empty-state">Không có cảnh báo.</div>';
    return;
  }
  list.innerHTML = snapshot.warnings.map(item => `<div class="warning ${escapeHtml(item.severity)}"><strong>${escapeHtml(item.code)}</strong><span>${escapeHtml(item.message)}</span></div>`).join("");
}

function renderModelStatus(model = {}) {
  defaultModel = model;
  const mock = model.synthetic_prediction === true;
  const calibrated = model.unknown_calibrated === true;
  const backend = model.model_backend || "UNKNOWN";
  const selector = byId("comparison-model");
  for (const option of selector.options) {
    if (option.value === "smoothed_v3" || option.value === "fusion_v4") {
      option.disabled = !model[option.value]?.comparison;
    }
    else if (option.value !== "default") option.disabled = backend !== "RESCNN64_TORCH";
  }
  if (selector.selectedOptions[0]?.disabled) selector.value = "default";
  const title = mock ? "MODEL GIẢ LẬP" : `MODEL THẬT · ${backend}`;
  const detail = mock
    ? "Chỉ kiểm tra UI/API; kết quả không có giá trị nhận diện."
    : calibrated
      ? `Đã cấu hình ngưỡng similarity ${model.similarity_threshold} và margin ${model.margin_threshold}.`
      : "Đã chạy embedding thật nhưng chỉ xếp hạng vì ngưỡng Unknown chưa được hiệu chuẩn.";
  ["identity-model-banner", "comparison-model-banner"].forEach(id => {
    const banner = byId(id);
    if (!banner) return;
    if (id === "comparison-model-banner" && selector.value === "fusion_v4") {
      banner.classList.remove("real");
      banner.innerHTML = "<strong>RESCNN64 V4 · THỬ NGHIỆM</strong><span>Kết hợp điểm cosine của ba nhánh gốc, hiệu chỉnh baseline và làm mịn.</span>";
      return;
    }
    if (id === "comparison-model-banner" && selector.value === "smoothed_v3") {
      banner.classList.remove("real");
      banner.innerHTML = "<strong>RESCNN64 V3 · THỬ NGHIỆM</strong><span>Lọc nhẹ exposure rồi chạy bộ hiệu chỉnh đã huấn luyện trên tín hiệu làm mịn.</span>";
      return;
    }
    if (id === "comparison-model-banner" && selector.value === "learned_baseline_v2") {
      banner.classList.add("real");
      banner.innerHTML = "<strong>RESCNN64 V2 · BỘ HIỆU CHỈNH ĐÃ HỌC</strong><span>Hiệu chỉnh exposure từ toàn bộ baseline, sau đó tính embedding bằng CNN gốc.</span>";
      return;
    }
    if (id === "comparison-model-banner" && byId("comparison-model").value === "baseline_v2") {
      banner.classList.remove("real");
      banner.innerHTML = "<strong>RESCNN64 V2 · THỬ NGHIỆM</strong><span>Dùng checkpoint đã huấn luyện với cách hiệu chỉnh exposure từ toàn bộ baseline.</span>";
      return;
    }
    banner.classList.toggle("real", !mock);
    banner.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span>`;
  });
}

function phaseGuidance(phase) {
  return ({
    IDLE: "Bấm Bắt đầu phiên để kết nối thiết bị và bắt đầu ghi.",
    MONITOR: "Hệ thống đang ghi và chờ bắt đầu một lượt mới.",
    BASELINE: "Đang đo baseline qua đầu lấy mẫu; chờ đủ thời gian.",
    WAIT_EXPOSURE: "Đặt mẫu vào vị trí rồi xác nhận bắt đầu exposure.",
    EXPOSURE: "Đang đo phản ứng với mẫu; không chuyển pha sớm.",
    WAIT_RECOVERY: "Lấy mẫu ra rồi xác nhận chuyển sang khí lọc.",
    RECOVERY: "Đang đo phục hồi qua khí lọc.",
    WAIT_FINISH: "Recovery đã đủ; xác nhận hoàn thành lượt.",
    WAIT_NAME: "Đặt tên/ghi chú rồi nhấn Lưu mẫu để chốt export và trở về MONITOR.",
    OFF: "Phần cứng đang dừng: bơm và van OFF; web server vẫn hoạt động. Nhấn Bật lại hệ thống để tiếp tục.",
    ERROR: "Phiên đã lỗi và output phải ở trạng thái OFF.",
    CLOSED: "Phiên đã đóng."
  })[phase] || "Đang đồng bộ trạng thái.";
}

function renderConfiguration(snapshot) {
  const config = snapshot.configuration || {};
  byId("config-baseline").textContent = `${formatNumber(config.baseline_s, 0)} s`;
  byId("config-exposure").textContent = `${formatNumber(config.exposure_s, 0)} s`;
  byId("config-recovery").textContent = `${formatNumber(config.recovery_s, 0)} s`;
  byId("config-pump").textContent = `${formatNumber(config.pump_pwm_pct, 0)}%`;
  [["duration-baseline", config.baseline_s], ["duration-exposure", config.exposure_s],
   ["duration-recovery", config.recovery_s]].forEach(([id, value]) => {
    const input = byId(id);
    if (input && document.activeElement !== input && value !== null && value !== undefined) input.value = String(value);
  });
  byId("duration-save").disabled = !config.runtime_editable;
  byId("config-note").textContent = config.runtime_editable
    ? "Cấu hình chỉ được áp dụng khi core/MCU xác nhận trước khi bắt đầu lượt."
    : `Cấu hình ${config.source || "core"} đang khóa; web không thay đổi thời gian hoặc PWM giữa phiên.`;
}

function renderPhase(snapshot) {
  byId("control-phase").textContent = snapshot.phase;
  byId("phase-guidance").textContent = phaseGuidance(snapshot.phase);
  byId("countdown-value").textContent = snapshot.remaining_s === null ? "Đang chờ" : `${formatNumber(snapshot.remaining_s, 1)} s`;
  const trial = snapshot.trial;
  const displayPhase = snapshot.phase === "MONITOR" && !trial ? "MONITOR" : snapshot.phase;
  const currentIndex = phases.indexOf(displayPhase);
  byId("phase-track").innerHTML = phases.map((phase, index) => {
    const label = phase === "MONITOR_NEXT" ? "MONITOR tiếp" : phase;
    const klass = index === currentIndex ? "active" : index < currentIndex ? "done" : "";
    return `<div class="phase-step ${klass}">${escapeHtml(label)}</div>`;
  }).join("");
  document.querySelectorAll("[data-command]").forEach(button => {
    const action = button.dataset.command;
    button.disabled = !snapshot.actions[action];
  });
  if (state.pendingSavedTrial && snapshot.phase === "MONITOR" && !snapshot.trial) {
    state.savedTrial = state.pendingSavedTrial;
    state.pendingSavedTrial = null;
    renderSavedTrial();
    loadTrials();
  }
}

function renderSavedTrial() {
  const trial = state.savedTrial;
  if (!trial) return;
  const complete = trial.status === "COMPLETE";
  byId("saved-sample-card").hidden = false;
  byId("saved-sample-name").textContent = trial.name || "Chưa đặt tên";
  byId("saved-sample-id").textContent = trial.trial_id;
  byId("saved-sample-status").textContent = complete
    ? "COMPLETE · có thể dùng để kiểm tra danh tính"
    : `${trial.status || "ABORTED"} · lượt dừng sớm, không dùng làm mẫu model hoàn chỉnh`;
  byId("predict-saved-button").disabled = !complete;
  byId("predict-saved-button").textContent = complete ? "Kiểm tra danh tính" : "Không thể dự đoán";
  byId("predict-saved-button").title = complete ? "" : "Chỉ mẫu COMPLETE mới được đưa vào model";
}

function renderTimeline(snapshot) {
  const events = snapshot.events.slice(-16).reverse();
  byId("event-timeline").innerHTML = events.length ? events.map(item => {
    const label = item.details?.next || item.details?.text || item.event;
    return `<div class="timeline-item"><time>${formatNumber(item.effective_mono_s, 1)} s</time><span>${escapeHtml(label)}</span></div>`;
  }).join("") : '<div class="empty-state">Chưa có event.</div>';
}

function renderSessionControls(snapshot) {
  const status = snapshot?.session_status;
  byId("session-controls").hidden = !status;
  if (!status) return;
  const off = snapshot.device.off_confirmed;
  const labels = {
    IDLE: "Chưa mở phiên",
    STARTING: "Đang kiểm tra thiết bị và khởi tạo log",
    RUNNING: "Phiên đang mở",
    STOPPING: "Đang tắt phần cứng và đóng log",
    ENDED: "Đã đóng phiên"
  };
  byId("session-state").textContent = status === "ENDED" && snapshot.mode === "HARDWARE"
    ? (off ? "Đã đóng phiên · MCU đã xác nhận lệnh OFF" : "Đã đóng phiên · Chưa nhận xác nhận OFF")
    : labels[status];
  document.querySelectorAll("[data-session-action]").forEach(button => {
    button.disabled = !state.connected || state.sessionRequestPending || !snapshot.actions[button.dataset.sessionAction];
  });
}

function renderOverview(snapshot) {
  const heartbeat = snapshot.device.heartbeat_healthy;
  byId("mode-badge").textContent = snapshot.mode;
  byId("phase-badge").textContent = snapshot.phase;
  byId("device-status").textContent = snapshot.device.fault ? "Lỗi đã latch" : heartbeat ? "Đang hoạt động" : "Đang chờ dữ liệu";
  byId("device-detail").textContent = snapshot.device.startup ? `Startup: ${snapshot.device.startup}` : `Phase owner: ${snapshot.mode === "SIMULATED" ? "simulation engine" : "MCU"}`;
  byId("pump-value").textContent = snapshot.outputs.pump_pwm_pct == null ? "—" : `${snapshot.outputs.pump_pwm_pct}% PWM`;
  byId("route-value").textContent = snapshot.outputs.air_path_commanded || "—";
  byId("valve-value").textContent = snapshot.outputs.valve_energized == null ? "Van —"
    : `Van ${snapshot.outputs.valve_energized ? "ON / B" : "OFF / A"}`;
  byId("writer-status").textContent = snapshot.writer?.status || "—";
  byId("writer-detail").textContent = `${snapshot.writer?.rows_written ?? 0} dòng · queue ${snapshot.writer?.queue_depth ?? 0}`;
  byId("heartbeat-value").textContent = heartbeat ? "Khỏe" : "Chờ / dừng";
  byId("sample-count").textContent = String(snapshot.device.sample_count ?? 0);
  byId("health-counts").textContent = `${snapshot.device.gaps} / ${snapshot.device.stale} / ${snapshot.device.errors}`;
  byId("quality-value").textContent = snapshot.quality?.overall || "—";
  const info = snapshot.device_info || {};
  byId("device-port").textContent = `${info.port || "Không dùng COM"} · ${info.transport || snapshot.mode}`;
  byId("device-firmware").textContent = [info.firmware_version, info.firmware_revision].filter(Boolean).join(" · ") || "—";
  byId("device-boot").textContent = info.boot_id || "—";
  byId("device-ads").textContent = `${formatAddress(info.ads_address, "0x48")} · ${info.ads_bus || "GPIO10/GPIO11"}`;
  byId("device-bme").textContent = `${formatAddress(info.bme_address, "0x77")} · ${info.bme_bus || "GPIO8/GPIO9"}`;
  byId("device-profile").textContent = `${info.profile_id || "—"} · ${formatNumber(info.sampling_hz, 0)} Hz`;
  byId("device-count").textContent = `${snapshot.device.physical_sensor_count ?? 5} thiết bị · ${snapshot.device.signal_count ?? snapshot.sensors.length} đại lượng`;
  byId("session-path").textContent = snapshot.writer?.path || "—";
  byId("last-update").textContent = `Cập nhật ${new Date().toLocaleTimeString("vi-VN")}`;
  renderModelStatus(snapshot.model);
  renderWarnings(snapshot);
  renderSessionControls(snapshot);
  renderPhase(snapshot);
  renderConfiguration(snapshot);
  renderTimeline(snapshot);
}

function chartLegend(target, definitions) {
  byId(target).innerHTML = definitions.map((item, index) => `<span style="--swatch:${chartColors[index]}">${escapeHtml(item.label)}</span>`).join("");
}

function drawChart(canvas, definitions, normalized, showPhases = false) {
  const snapshot = state.snapshot;
  if (!snapshot || canvas.offsetParent === null) return;
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 10) return;
  const ratio = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  const width = rect.width, height = rect.height;
  const padding = {left: 62, right: 16, top: 16, bottom: 32};
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#72878b";
  ctx.font = "12px system-ui";
  ctx.lineWidth = 1;
  const series = definitions.map(item => ({...item, points: snapshot.series[item.signal] || []}));
  const allTimes = series.flatMap(item => item.points.map(point => point[0]));
  const minX = allTimes.length ? Math.min(...allTimes) : snapshot.now - snapshot.window_s;
  const maxX = allTimes.length ? Math.max(...allTimes) : snapshot.now;
  let minY = 0, maxY = 1;
  if (!normalized) {
    const values = series.flatMap(item => item.points.map(point => point[1]).filter(value => value !== null));
    if (values.length) {
      minY = Math.min(...values); maxY = Math.max(...values);
      const margin = Math.max((maxY - minY) * .12, .01);
      minY -= margin; maxY += margin;
    }
  }
  const xScale = value => padding.left + (value - minX) / Math.max(.001, maxX - minX) * plotW;
  const yScale = value => padding.top + (1 - (value - minY) / Math.max(.000001, maxY - minY)) * plotH;
  const yRange = maxY - minY;
  const yDigits = normalized ? 0 : yRange < .1 ? 3 : yRange < 10 ? 2 : 1;
  for (let i = 0; i <= 4; i++) {
    const y = padding.top + plotH * i / 4;
    const tick = maxY - yRange * i / 4;
    ctx.strokeStyle = i === 0 || i === 4 ? "#314952" : "#243841";
    ctx.beginPath(); ctx.moveTo(padding.left, y); ctx.lineTo(width - padding.right, y); ctx.stroke();
    ctx.fillStyle = "#82969a"; ctx.textAlign = "right";
    ctx.fillText(normalized ? `${Math.round(tick * 100)}%` : tick.toFixed(yDigits), padding.left - 9, y + 4);
  }
  for (let i = 0; i <= 2; i++) {
    const x = padding.left + plotW * i / 2;
    const tick = minX + (maxX - minX) * i / 2;
    ctx.strokeStyle = "rgba(36,56,65,.55)";
    ctx.beginPath(); ctx.moveTo(x, padding.top); ctx.lineTo(x, padding.top + plotH); ctx.stroke();
    ctx.fillStyle = "#82969a";
    ctx.textAlign = i === 0 ? "left" : i === 2 ? "right" : "center";
    ctx.fillText(`${Math.round(tick)} s`, x, height - 7);
  }
  if (showPhases) {
    snapshot.events.filter(event => event.event === "phase_change" && event.effective_mono_s >= minX && event.effective_mono_s <= maxX).forEach(event => {
      const x = xScale(event.effective_mono_s);
      ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = "rgba(232,198,106,.7)";
      ctx.beginPath(); ctx.moveTo(x, padding.top); ctx.lineTo(x, padding.top + plotH); ctx.stroke();
      ctx.setLineDash([]); ctx.translate(x + 4, padding.top + 5); ctx.rotate(Math.PI / 2);
      ctx.fillStyle = "#d9c678"; ctx.font = "10px system-ui";
      ctx.fillText(String(event.details?.next || "PHASE"), 0, 0); ctx.restore();
    });
  }
  ctx.textAlign = "left";
  series.forEach((item, index) => {
    const values = item.points.map(point => point[1]).filter(value => value !== null);
    const localMin = normalized && values.length ? Math.min(...values) : minY;
    const localMax = normalized && values.length ? Math.max(...values) : maxY;
    ctx.strokeStyle = chartColors[item.colorIndex ?? index]; ctx.lineWidth = 2.4; ctx.beginPath();
    let drawing = false;
    item.points.forEach(([x, raw]) => {
      if (raw === null) { drawing = false; return; }
      const value = normalized ? (raw - localMin) / Math.max(.000001, localMax - localMin) : raw;
      const px = xScale(x), py = yScale(value);
      if (!drawing) { ctx.moveTo(px, py); drawing = true; } else { ctx.lineTo(px, py); }
    });
    ctx.stroke();
  });
}

function drawCharts(snapshot) {
  state.snapshot = snapshot;
  renderSignalCharts("realtime-chart-grid", "realtime", snapshot.sensors);
  renderSignalCharts("collection-chart-grid", "collection", snapshot.sensors);
}

function renderSignalCharts(gridId, prefix, signals) {
  const grid = byId(gridId);
  if (!grid) return;
  if (grid.children.length !== signals.length) {
    grid.innerHTML = signals.map((item, index) => `<article class="panel chart-panel mini-chart" id="${prefix}-card-${index}">
      <div class="panel-head"><h2>${escapeHtml(item.label)}</h2><span>${escapeHtml(item.unit)}</span></div>
      <div class="mini-reading"><strong id="${prefix}-value-${index}">—</strong><span>${escapeHtml(item.unit)}</span></div>
      <div class="mini-quality" id="${prefix}-quality-${index}">Đang chờ dữ liệu</div>
      <canvas id="${prefix}-chart-${index}" role="img" aria-label="Biểu đồ ${escapeHtml(item.label)}"></canvas>
    </article>`).join("");
  }
  signals.forEach((definition, index) => {
    byId(`${prefix}-card-${index}`).style.setProperty("--sensor-color", chartColors[index % chartColors.length]);
    const decimals = definition.unit === "hPa" ? 2 : definition.unit === "%RH" || definition.unit === "°C" ? 3 : 4;
    byId(`${prefix}-value-${index}`).textContent = formatNumber(definition.value, decimals);
    const quality = definition.quality || {};
    const count = definition.adc_count !== null && definition.adc_count !== undefined ? ` · ${definition.adc_count} ct` : "";
    byId(`${prefix}-quality-${index}`).textContent = `${quality.status || "—"}${count} · valid ${quality.valid_n ?? 0}/${quality.n ?? 0}`;
    drawChart(byId(`${prefix}-chart-${index}`), [{...definition, colorIndex: index}], false, false);
  });
}

async function pollSnapshot() {
  try {
    const windowSize = byId("window-select").value;
    const snapshot = await api(`/api/snapshot?window=${encodeURIComponent(windowSize)}`);
    state.snapshot = snapshot;
    setConnection(true);
    renderOverview(snapshot);
    drawCharts(snapshot);
  } catch (error) {
    setConnection(false, error.message);
    renderSessionControls(state.snapshot);
  }
}

async function pollMessages() {
  try {
    const payload = await api(`/api/messages?after=${state.messageAfter}`);
    if (!payload.messages.length) return;
    const log = byId("message-log");
    if (!state.messageAfter) log.replaceChildren();
    payload.messages.forEach(item => {
      state.messageAfter = Math.max(state.messageAfter, item.sequence);
      const row = document.createElement("div");
      row.className = `message-item ${item.level === "MODEL" ? "model" : ""}`;
      row.innerHTML = `<time>${new Date(item.at).toLocaleTimeString("vi-VN")}</time><span>${escapeHtml(item.text)}</span>`;
      log.prepend(row);
    });
    while (log.children.length > 40) log.lastElementChild.remove();
    byId("message-sequence").textContent = String(state.messageAfter);
  } catch { /* Snapshot polling owns the visible connection state. */ }
}

function renderIdentity(result) {
  const scores = Array.isArray(result.ranking) ? result.ranking : (result.predicted_id ?
    [{label: result.predicted_id, similarity: result.confidence ?? result.similarity}] : []);
  const ranking = [...scores].sort((a, b) => b.similarity - a.similarity).slice(0, 3);
  const scoreLabel = result.synthetic_prediction ? "Điểm giả lập" : "Cosine";
  const rows = ranking.map((item, index) => `<div class="identity-rank-item ${index === 0 ? "top" : ""}">
    <span class="rank-number">${index + 1}</span><div class="rank-identity"><strong>${escapeHtml(item.label)}</strong>
      ${item.reference_path ? `<code>${escapeHtml(item.reference_path.split("/").at(-1))}</code>` : ""}</div>
    <div class="score-scale-head"><span>${scoreLabel}</span><strong>${formatNumber(item.similarity, 4)}</strong></div>
  </div>`).join("");
  const note = result.status === "UNKNOWN" ? "Mẫu dưới ngưỡng nhận diện." : result.status === "RANKED_ONLY"
    ? "Ngưỡng xác nhận danh tính chưa được hiệu chuẩn." : "";
  byId("identity-result").innerHTML = `<h2>Ba lớp có điểm cao nhất</h2><code>${escapeHtml(result.sample_id)}</code>
    <div class="identity-ranking">${rows || '<div class="empty-state">Không có lớp để xếp hạng.</div>'}</div>
    ${note ? `<p>${note}</p>` : ""}`;
}

function smoothingLabel(method) {
  return ({light3: "trung bình có trọng số 3 điểm", sg5_half: "Savitzky–Golay 5 điểm, pha 50%"})[method] || method;
}

function coffeeSamples() {
  return state.trials.filter(item => canCompare(item) && item.mode === "HARDWARE" && savedSelection.has(item.trial_id));
}

function renderCoffeeSelection() {
  const samples = coffeeSamples();
  const skipped = eligibleSelection(savedSelection).length - samples.length;
  byId("coffee-selection-status").textContent = samples.length
    ? `${samples.length} mẫu hardware đã lưu lựa chọn${skipped ? ` · Bỏ qua ${skipped} mẫu mô phỏng` : ""}`
    : "Chọn và lưu mẫu hardware trong mục 05 · Danh sách mẫu.";
  byId("coffee-button").disabled = coffeeBusy || !samples.length;
}

function renderCoffeeBatch(rows) {
  byId("coffee-result").innerHTML = `<div class="table-wrap"><table class="sample-table">
    <thead><tr><th>Model</th><th>Tên mẫu</th><th>Trial ID</th><th>Kết quả</th><th>Đối chiếu tên mẫu</th><th>Chi tiết</th></tr></thead>
    <tbody>${rows.map(row => {
      const result = row.result;
      const label = result?.status === "PREDICTED"
        ? (result.has_coffee ? "Có mùi cà phê" : "Không có mùi cà phê")
        : result ? "Không thể kiểm tra" : row.running ? "Đang kiểm tra…" : "Chờ kiểm tra";
      const detail = result?.status === "PREDICTED"
        ? `${result.model || ""}${Number.isFinite(result.logit) ? ` · Logit ${formatNumber(result.logit, 4)}` : ""}`
        : result?.reason || "";
      const expected = /cf/i.test(row.name || "");
      const correct = result?.status === "PREDICTED" && result.has_coffee === expected;
      const verdict = result?.status === "PREDICTED"
        ? `<span class="coffee-verdict ${correct ? "correct" : "incorrect"}">${correct ? "✓ Đúng" : "✕ Sai"}</span>`
        : '<span class="coffee-verdict pending">— Chưa đánh giá</span>';
      return `<tr><td>${escapeHtml(row.modelName)}</td><td><strong>${escapeHtml(row.name || "Chưa đặt tên")}</strong></td>
        <td><code>${escapeHtml(row.trial_id)}</code></td><td>${label}</td>
        <td>${verdict}<small class="coffee-expected">${expected ? "Có CF · Có cà phê" : "Không có CF · Không cà phê"}</small></td>
        <td>${escapeHtml(detail)}</td></tr>`;
    }).join("")}</tbody></table></div>`;
}

async function runIdentity(sampleId) {
  const request = ++identityRequest;
  identityJob = null;
  const target = byId("identity-result");
  target.textContent = "Đang xếp hạng danh tính…";
  try {
    const job = await api("/api/inference/identity", {method: "POST", body: JSON.stringify({sample_id: sampleId})});
    if (request === identityRequest) identityJob = job.job_id;
  } catch (error) {
    if (request === identityRequest) target.textContent = error.message;
  }
}

function coffeeMetrics(rows) {
  const predicted = rows.filter(row => row.result?.status === "PREDICTED");
  const positives = predicted.filter(row => /cf/i.test(row.name || ""));
  const correct = predicted.filter(row => row.result.has_coffee === /cf/i.test(row.name || "")).length;
  const tp = positives.filter(row => row.result.has_coffee).length;
  return {predicted: predicted.length, correct, tp, positives: positives.length,
    failed: rows.filter(row => row.result && row.result.status !== "PREDICTED").length};
}

function renderCoffeeMetrics(groups) {
  byId("coffee-metrics").innerHTML = `<div class="coffee-metrics-table"><table class="sample-table">
    <thead><tr><th>Model</th><th>Accuracy</th><th>Recall cà phê</th><th>Đã dự đoán</th><th>Lỗi</th></tr></thead>
    <tbody>${groups.map(group => {
      const m = coffeeMetrics(group.rows);
      const accuracy = m.predicted ? `${formatNumber(100 * m.correct / m.predicted, 1)}% (${m.correct}/${m.predicted})` : "—";
      const recall = m.positives ? `${formatNumber(100 * m.tp / m.positives, 1)}% (${m.tp}/${m.positives})` : "—";
      return `<tr><td>${escapeHtml(group.name)}</td><td>${accuracy}</td><td>${recall}</td>
        <td>${m.predicted}/${group.rows.length}</td><td>${m.failed}</td></tr>`;
    }).join("")}</tbody></table></div>
    <p class="result-trace">Nhãn có cà phê khi tên chứa CF, không phân biệt hoa thường.
      Accuracy = số dự đoán đúng / số mẫu dự đoán thành công.
      Recall = số mẫu CF được phát hiện / số mẫu CF dự đoán thành công.
      Mẫu lỗi được đếm riêng. Dấu — khi chưa có mẫu để tính.</p>`;
}

async function runCoffee() {
  if (coffeeBusy) return;
  const samples = coffeeSamples();
  if (!samples.length) return;
  const groups = coffeeModels.map(model => ({
    ...model, rows: samples.map(item => ({
      trial_id: item.trial_id, name: item.name, modelName: model.name, result: null
    }))
  }));
  const rows = groups.flatMap(group => group.rows);
  coffeeBusy = true;
  renderCoffeeSelection();
  renderCoffeeMetrics(groups);
  try {
    let completed = 0;
    for (const group of groups) {
      for (const row of group.rows) {
        row.running = true;
        byId("coffee-progress").textContent = `${group.name} · Đang kiểm tra ${completed + 1}/${rows.length} lượt`;
        renderCoffeeBatch(rows);
        try {
          const submitted = await api("/api/inference/coffee", {method: "POST", body: JSON.stringify({
            sample_id: row.trial_id, model: group.id
          })});
          const deadline = Date.now() + 120000;
          while (!row.result) {
            const payload = await api("/api/inference/results?after=0");
            const job = payload.jobs.find(item => item.job_id === submitted.job_id);
            if (job && ["SUCCEEDED", "FAILED"].includes(job.state)) {
              row.result = job.result || {reason: job.error || "Kiểm tra thất bại."};
            } else {
              if (Date.now() >= deadline) throw new Error("Quá thời gian chờ kết quả.");
              await new Promise(resolve => setTimeout(resolve, 700));
            }
          }
        } catch (error) {
          row.result = {reason: error.message};
        }
        row.running = false;
        completed++;
        renderCoffeeBatch(rows);
        renderCoffeeMetrics(groups);
      }
    }
    byId("coffee-progress").textContent = `Hoàn tất cả 3 model trên ${samples.length} mẫu đã chọn.`;
  } finally {
    coffeeBusy = false;
    renderCoffeeSelection();
  }
}

function renderComparison(result) {
  const names = new Map(state.trials.map(item => [item.trial_id, item.name || "Chưa đặt tên"]));
  const ranking = result.ranking.map(item => {
    const score = Number(item.similarity);
    const direction = score < 0 ? "negative" : "positive";
    return `<div class="rank-item">
      <span class="rank-number">${item.rank}</span>
      <div class="rank-identity"><strong>${escapeHtml(names.get(item.candidate_id) || `Mẫu ${item.input_order}`)}</strong><code>${escapeHtml(item.candidate_id)}</code>
        ${item.blank_id ? `<small>Blank: ${escapeHtml(names.get(item.blank_id) || item.blank_id)}</small>` : ""}</div>
      <div class="score-scale ${direction}" aria-label="Cosine similarity ${formatNumber(score, 4)} trên thang âm 1 đến 1">
        <div class="score-scale-head"><span>Cosine similarity</span><strong>${formatNumber(score, 4)}</strong></div>
        <div class="rank-track"><em></em><i></i><b></b></div>
        <div class="score-scale-labels"><span>-1</span><span>0</span><span>1</span></div>
      </div>
    </div>`;
  }).join("");
  const skipped = (result.skipped_candidates || []).map(item => `<li>
    <strong>${escapeHtml(names.get(item.candidate_id) || item.candidate_id)}</strong>
    <code>${escapeHtml(item.candidate_id)}</code> · ${escapeHtml(item.reason)}
  </li>`).join("");
  const warnings = (result.reference_warnings || []).length + result.ranking.reduce((total, item) => total + (item.warnings || []).length, 0);
  const preprocessing = result.preprocessing_mode === "fusion_v4"
    ? `V4 thử nghiệm · Trọng số cosine V1 / V2 / V3: ${result.fusion_weights.map(weight => formatNumber(weight * 100, 0) + "%").join(" / ")}.`
    : result.preprocessing_mode === "smoothed_v3"
    ? `V3 thử nghiệm · Làm mịn exposure bằng ${smoothingLabel(result.smoothing)} trước bộ hiệu chỉnh. CNN dùng trọng số gốc.`
    : result.preprocessing_mode === "learned_baseline"
    ? "Bộ hiệu chỉnh đã học dự đoán mức bù và độ dốc cho từng kênh. Trọng số ResCNN64 giữ nguyên."
    : result.preprocessing_mode === "matched_blank"
    ? `Trừ đường blank cùng phiên. Blank của mẫu tham chiếu: ${names.get(result.reference_blank_id) || result.reference_blank_id}.`
    : "Chưa có blank phù hợp cho tất cả các phiên trong lần chạy này. V2 bù xu hướng baseline có giới hạn.";
  const target = byId("comparison-result");
  target.innerHTML = `${result.experimental ? `<div class="result-trace">${escapeHtml(preprocessing)}</div>` : ""}
    ${ranking || '<div class="empty-state">Không có mẫu đủ dữ liệu để xếp hạng.</div>'}
    ${skipped ? `<div class="result-trace"><strong>Mẫu chưa xếp hạng</strong><ul>${skipped}</ul></div>` : ""}
    <div class="result-trace">Model ${escapeHtml(result.model_id)} · ${escapeHtml(result.model_backend)}${result.experimental ? "" : ` · ${warnings} cảnh báo QC/tiền xử lý`}</div>`;
  target.querySelectorAll(".rank-track").forEach((track, index) => {
    const score = Math.max(-1, Math.min(1, Number(result.ranking[index].similarity)));
    const position = (score + 1) * 50;
    track.style.setProperty("--score-position", `${position}%`);
    track.style.setProperty("--score-segment-start", `${Math.min(50, position)}%`);
    track.style.setProperty("--score-segment-width", `${Math.abs(score) * 50}%`);
  });
  target.scrollTop = 0;
}

async function pollInference() {
  try {
    // Jobs are mutable while QUEUED/PREDICTING, so poll the bounded cache and
    // deduplicate terminal results by job_id instead of advancing past a job.
    const payload = await api("/api/inference/results?after=0");
    payload.jobs.forEach(job => {
      if (state.renderedJobs.has(job.job_id) || !["SUCCEEDED", "FAILED"].includes(job.state)) return;
      if (job.task === "identity" && identityJob !== undefined && job.job_id !== identityJob) return;
      if (job.task === "coffee") return;
      if (job.task === "reference_comparison" && job.job_id !== comparisonJob) return;
      state.renderedJobs.add(job.job_id);
      if (job.task === "reference_comparison") {
        comparisonJob = undefined;
        comparisonBusy = false;
        byId("comparison-model").disabled = false;
        renderComparisonSelection();
      }
      if (job.state === "FAILED") {
        const target = job.task === "identity" ? byId("identity-result") : byId("comparison-result");
        target.innerHTML = `<div class="empty-state">${escapeHtml(job.error || "Inference failed")}</div>`;
      } else if (job.result.task === "identity") renderIdentity(job.result);
      else if (job.result.task === "reference_comparison") renderComparison(job.result);
    });
  } catch { /* Inference status is also visible through the dashboard warning list. */ }
}

async function loadTrials() {
  try {
    const payload = await api("/api/trials");
    state.trials = payload.trials;
    if (state.savedTrial) {
      const finalized = payload.trials.find(item => item.trial_id === state.savedTrial.trial_id);
      if (finalized) state.savedTrial = finalized;
      if (finalized?.status === "COMPLETE" && finalized.export_finalized && autoPredictedTrial !== finalized.trial_id) {
        autoPredictedTrial = finalized.trial_id;
        byId("identity-sample").value = finalized.trial_id;
        if (!byId("page-control").hidden) document.querySelector('[data-page="identity"]').click();
        runIdentity(finalized.trial_id);
      }
    }
    const updatedCatalog = JSON.stringify(payload.trials);
    if (trialCatalogJson !== updatedCatalog) {
      trialCatalogJson = updatedCatalog;
      const options = eligible => eligible.map(item => `<option value="${escapeHtml(item.trial_id)}">${escapeHtml(item.name || "Chưa đặt tên")} · COMPLETE · QC ${escapeHtml(item.quality || "NOT_EVALUATED")}</option>`).join("");
      const complete = state.trials.filter(canCompare);
      byId("trial-options").innerHTML = options(complete);
      renderLibrary();
      renderComparisonSelection();
    }
    if (state.savedTrial) renderSavedTrial();
    return payload.trials;
  } catch { return state.trials; /* Catalog may be empty while the first trial is open. */ }
}

function canCompare(item) {
  return item.status === "COMPLETE" && item.export_finalized;
}

function readComparisonSelection() {
  try {
    const ids = JSON.parse(localStorage.getItem(selectionKey) || "[]");
    return new Set(Array.isArray(ids) ? ids.filter(id => typeof id === "string") : []);
  } catch {
    return new Set();
  }
}

function eligibleSelection(selection) {
  return state.trials.filter(item => canCompare(item) && selection.has(item.trial_id)).map(item => item.trial_id);
}

function referenceValue() {
  return byId("reference-id").value.trim().toLowerCase();
}

function renderComparisonSelection() {
  const draft = eligibleSelection(draftSelection);
  const saved = eligibleSelection(savedSelection);
  const unsaved = draft.length !== savedSelection.size || draft.some(id => !savedSelection.has(id));
  byId("save-comparison-selection").disabled = trialCatalogJson === undefined || !unsaved;
  const eligibleCount = state.trials.filter(canCompare).length;
  const toggle = byId("toggle-comparison-selection");
  toggle.disabled = trialCatalogJson === undefined || eligibleCount === 0;
  toggle.textContent = eligibleCount > 0 && draft.length === eligibleCount ? "Bỏ chọn tất cả" : "Chọn tất cả";
  const libraryStatus = unsaved ? `Đang chọn ${draft.length} mẫu · Chưa lưu thay đổi` : `Đã lưu ${saved.length} mẫu`;
  feedback("library-selection-status", libraryStatus);

  const includesReference = saved.includes(referenceValue());
  const candidateCount = saved.length - Number(includesReference);
  const unavailable = savedSelection.size - saved.length;
  const notes = [`${candidateCount} mẫu đã lưu để đối sánh`];
  if (includesReference) notes.push("đã loại mẫu tham chiếu khỏi danh sách");
  if (trialCatalogJson !== undefined && unavailable) notes.push(`${unavailable} mẫu đã lưu hiện không khả dụng`);
  byId("comparison-selection-status").textContent = notes.join(" · ");
  byId("comparison-button").disabled = comparisonBusy || candidateCount === 0;
  renderCoffeeSelection();
}

function saveComparisonSelection() {
  const selection = eligibleSelection(draftSelection);
  try {
    localStorage.setItem(selectionKey, JSON.stringify(selection));
    savedSelection = new Set(selection);
    draftSelection = new Set(selection);
    renderComparisonSelection();
  } catch {
    feedback("library-selection-status", "Trình duyệt không lưu được lựa chọn. Hãy thử lại.", true);
  }
}

function toggleComparisonSelection() {
  const eligible = state.trials.filter(canCompare).map(item => item.trial_id);
  draftSelection = new Set(eligible.every(id => draftSelection.has(id)) ? [] : eligible);
  byId("sample-library-body").querySelectorAll("[data-select-trial]").forEach(checkbox => {
    checkbox.checked = !checkbox.disabled && draftSelection.has(checkbox.dataset.selectTrial);
  });
  renderComparisonSelection();
}

function renderLibrary() {
  const body = byId("sample-library-body");
  if (!body) return;
  const query = byId("library-search").value.trim().toLowerCase();
  const status = byId("library-status").value;
  const rows = state.trials.filter(item => {
    const matchesText = !query || `${item.name || ""} ${item.trial_id}`.toLowerCase().includes(query);
    return matchesText && (status === "ALL" || item.status === status);
  });
  body.innerHTML = rows.map(item => {
    const complete = canCompare(item);
    const source = item.mode === "HARDWARE" ? "HARDWARE" : item.mode;
    const name = escapeHtml(item.name || "Chưa đặt tên");
    const id = escapeHtml(item.trial_id);
    return `<tr>
      <td class="select-trial-cell"><input type="checkbox" data-select-trial="${id}" aria-label="Chọn mẫu ${name} (${id})" ${complete && draftSelection.has(item.trial_id) ? "checked" : ""} ${complete ? "" : 'disabled title="Mẫu cần được lưu hoàn chỉnh"'}></td>
      <td><strong>${name}</strong></td>
      <td><code>${id}</code></td>
      <td><span class="source-pill ${source === "HARDWARE" ? "hardware" : ""}">${escapeHtml(source)}</span></td>
      <td><span class="status-pill ${complete ? "complete" : "aborted"}">${escapeHtml(item.status)}</span></td>
      <td>${escapeHtml(item.quality || "NOT_EVALUATED")}</td>
      <td>${escapeHtml(item.started_at ? new Date(item.started_at).toLocaleString("vi-VN") : "—")}</td>
      <td><div class="table-actions"><button type="button" data-copy-trial="${escapeHtml(item.trial_id)}">Sao chép</button><button type="button" data-predict-trial="${escapeHtml(item.trial_id)}" ${complete ? "" : "disabled"}>Dự đoán</button></div></td>
    </tr>`;
  }).join("");
  byId("library-empty").hidden = rows.length > 0;
}

async function sendCommand(action, argument = "") {
  const result = await api("/api/commands", {method: "POST", body: JSON.stringify({action, argument, request_id: requestId()})});
  byId("global-alert").hidden = true;
  return result;
}

function feedback(id, message, error = false) {
  const target = byId(id);
  if (!target) return;
  target.textContent = message;
  target.classList.toggle("error", error);
}

function initControls() {
  document.querySelectorAll("[data-session-action]").forEach(button => {
    button.addEventListener("click", async () => {
      const action = button.dataset.sessionAction;
      if (action === "end_session" && state.snapshot?.trial?.status === "ACTIVE" &&
          !confirm("Kết thúc phiên khi đang thu sẽ dừng lượt hiện tại. Tiếp tục?")) return;
      state.sessionRequestPending = true;
      renderSessionControls(state.snapshot);
      feedback("session-feedback", "");
      try {
        await sendCommand(action);
        if (action === "begin_session") byId("saved-sample-card").hidden = true;
        state.pendingSavedTrial = null;
        await pollSnapshot();
      } catch (error) {
        feedback("session-feedback", error.message, true);
      } finally {
        state.sessionRequestPending = false;
        renderSessionControls(state.snapshot);
      }
    });
  });
  document.querySelectorAll("[data-command]").forEach(button => {
    button.addEventListener("click", async () => {
      const action = button.dataset.command;
      let argument = "";
      if (action === "name") argument = byId("sample-name").value;
      if (action === "notes") argument = byId("sample-notes").value;
      if (action === "mark") argument = byId("marker-text").value;
      if (action === "pause" && !confirm("Dừng bơm và van? Web server vẫn chạy và có thể bật lại.")) return;
      if (action === "next" && state.snapshot?.trial) {
        state.pendingSavedTrial = {...state.snapshot.trial};
      }
      const feedbackId = ["name", "notes"].includes(action) ? "metadata-feedback" : "collection-feedback";
      try {
        await sendCommand(action, argument);
        const messages = {name: "Đã gửi yêu cầu lưu tên mẫu.", notes: "Đã gửi yêu cầu lưu ghi chú.",
          next: "Đã gửi yêu cầu lưu mẫu; đang chờ core xác nhận.", abort: "Đã gửi yêu cầu hủy lượt."};
        feedback(feedbackId, messages[action] || `Đã gửi lệnh ${action}.`);
      } catch (error) {
        feedback(feedbackId, error.message, true);
        byId("global-alert").hidden = false; byId("global-alert").textContent = error.message;
      }
    });
  });
  byId("duration-save").addEventListener("click", async () => {
    const values = ["duration-baseline", "duration-exposure", "duration-recovery"].map(id => Number(byId(id).value));
    if (values.some(value => !Number.isFinite(value) || value < 1 || value > 3600)) {
      feedback("duration-feedback", "Mỗi thời gian phải nằm trong khoảng 1–3600 giây.", true); return;
    }
    try {
      await sendCommand("configure", values.join(","));
      const modelWarning = values[0] === 60 && values[1] === 120 ? "" : " Lưu ý: model hiện tại chỉ nhận baseline 60 s và exposure 120 s.";
      feedback("duration-feedback", `Đã gửi cấu hình ${values.join(" / ")} giây; đang chờ MCU/core xác nhận.${modelWarning}`);
    } catch (error) { feedback("duration-feedback", error.message, true); }
  });
  byId("copy-trial-button").addEventListener("click", async () => {
    const value = state.savedTrial?.trial_id || "";
    try { await navigator.clipboard.writeText(value); byId("copy-trial-button").textContent = "Đã sao chép"; feedback("saved-feedback", "Đã sao chép trial_id vào clipboard."); }
    catch { byId("identity-sample").value = value; feedback("saved-feedback", "Không truy cập được clipboard; trial_id đã được điền vào ô dự đoán.", true); }
  });
  byId("predict-saved-button").addEventListener("click", () => {
    byId("identity-sample").value = state.savedTrial?.trial_id || "";
    document.querySelector('[data-page="identity"]').click();
  });
  byId("window-select").addEventListener("change", pollSnapshot);
  byId("control-window-select").addEventListener("change", () => {
    byId("window-select").value = byId("control-window-select").value;
    pollSnapshot();
  });
  byId("window-select").addEventListener("change", () => {
    byId("control-window-select").value = byId("window-select").value;
  });
  byId("identity-button").addEventListener("click", () => runIdentity(byId("identity-sample").value.trim()));
  byId("coffee-button").addEventListener("click", runCoffee);
  byId("reference-id").addEventListener("input", renderComparisonSelection);
  byId("comparison-model").addEventListener("change", () => renderModelStatus(defaultModel));
  byId("open-comparison-selection").addEventListener("click", () => {
    document.querySelector('[data-page="library"]').click();
  });
  byId("comparison-button").addEventListener("click", async () => {
    const referenceId = referenceValue();
    const candidates = eligibleSelection(savedSelection).filter(id => id !== referenceId);
    if (comparisonBusy || !candidates.length) return;
    const target = byId("comparison-result");
    if (!state.trials.some(item => item.trial_id === referenceId && canCompare(item))) {
      target.innerHTML = '<div class="empty-state">Hãy chọn một mẫu tham chiếu đã lưu hoàn chỉnh.</div>';
      return;
    }
    comparisonBusy = true;
    byId("comparison-model").disabled = true;
    renderComparisonSelection();
    target.innerHTML = '<div class="empty-state">Đang mã hóa và xếp hạng.</div>';
    try {
      const job = await api("/api/inference/compare", {method: "POST", body: JSON.stringify({
        reference_id: referenceId, candidate_ids: candidates, model: byId("comparison-model").value
      })});
      comparisonJob = job.job_id;
    } catch (error) {
      comparisonBusy = false;
      byId("comparison-model").disabled = false;
      renderComparisonSelection();
      target.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    }
  });
  byId("library-search").addEventListener("input", renderLibrary);
  byId("library-status").addEventListener("change", renderLibrary);
  byId("toggle-comparison-selection").addEventListener("click", toggleComparisonSelection);
  byId("save-comparison-selection").addEventListener("click", saveComparisonSelection);
  byId("sample-library-body").addEventListener("change", event => {
    const checkbox = event.target.closest("[data-select-trial]");
    if (!checkbox || checkbox.disabled) return;
    const id = checkbox.dataset.selectTrial;
    if (checkbox.checked) draftSelection.add(id);
    else draftSelection.delete(id);
    renderComparisonSelection();
  });
  byId("sample-library-body").addEventListener("click", async event => {
    const copy = event.target.closest("[data-copy-trial]");
    const predict = event.target.closest("[data-predict-trial]");
    if (copy) {
      try { await navigator.clipboard.writeText(copy.dataset.copyTrial); copy.textContent = "Đã sao chép"; }
      catch { byId("identity-sample").value = copy.dataset.copyTrial; }
    }
    if (predict) {
      byId("identity-sample").value = predict.dataset.predictTrial;
      document.querySelector('[data-page="identity"]').click();
    }
  });
}

function boot() {
  initNavigation();
  initControls();
  renderComparisonSelection();
  pollSnapshot(); pollMessages(); pollInference(); loadTrials();
  setInterval(pollSnapshot, 1000);
  setInterval(pollMessages, 700);
  setInterval(pollInference, 700);
  setInterval(loadTrials, 2000);
  window.addEventListener("resize", () => state.snapshot && drawCharts(state.snapshot));
}

document.addEventListener("DOMContentLoaded", boot);
