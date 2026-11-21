"use strict";

const state = { snapshot: null, messageAfter: 0, renderedJobs: new Set(), trials: [], connected: false, pendingSavedTrial: null, savedTrial: null };
const titles = {
  realtime: "Tín hiệu realtime",
  control: "Điều khiển thu mẫu",
  identity: "Dự đoán danh tính",
  comparison: "So sánh mùi tham chiếu",
  library: "Danh sách mẫu"
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
  byId("sidebar-status").textContent = online ? "Đã kết nối core" : "Mất kết nối web";
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
  const mock = model.synthetic_prediction === true;
  const calibrated = model.unknown_calibrated === true;
  const backend = model.model_backend || "UNKNOWN";
  const title = mock ? "MODEL GIẢ LẬP" : `MODEL THẬT · ${backend}`;
  const detail = mock
    ? "Chỉ kiểm tra UI/API; kết quả không có giá trị nhận diện."
    : calibrated
      ? `Đã cấu hình ngưỡng similarity ${model.similarity_threshold} và margin ${model.margin_threshold}.`
      : "Đã chạy embedding thật nhưng chỉ xếp hạng vì ngưỡng Unknown chưa được hiệu chuẩn.";
  ["identity-model-banner", "comparison-model-banner"].forEach(id => {
    const banner = byId(id);
    if (!banner) return;
    banner.classList.toggle("real", !mock);
    banner.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span>`;
  });
}

function phaseGuidance(phase) {
  return ({
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

function renderOverview(snapshot) {
  const heartbeat = snapshot.device.heartbeat_healthy;
  byId("mode-badge").textContent = snapshot.mode;
  byId("phase-badge").textContent = snapshot.phase;
  byId("device-status").textContent = snapshot.device.fault ? "Lỗi đã latch" : heartbeat ? "Đang hoạt động" : "Đang chờ dữ liệu";
  byId("device-detail").textContent = snapshot.device.startup ? `Startup: ${snapshot.device.startup}` : `Phase owner: ${snapshot.mode === "SIMULATED" ? "simulation engine" : "MCU"}`;
  byId("pump-value").textContent = `${snapshot.outputs.pump_pwm_pct ?? 0}% PWM`;
  byId("route-value").textContent = snapshot.outputs.air_path_commanded || "—";
  byId("valve-value").textContent = `Van ${snapshot.outputs.valve_energized ? "ON / B" : "OFF / A"}`;
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
  } catch (error) { setConnection(false, error.message); }
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
  const unknown = result.status === "UNKNOWN";
  const rankedOnly = result.status === "RANKED_ONLY";
  const answer = unknown ? "UNKNOWN" : rankedOnly ? `${result.top_candidate} · CHƯA XÁC NHẬN` : result.predicted_id;
  const rawScore = result.confidence ?? result.similarity;
  const width = result.confidence !== undefined
    ? Math.max(0, Math.min(100, Number(rawScore) * 100))
    : Math.max(0, Math.min(100, (Number(rawScore) + 1) * 50));
  const scoreText = result.confidence !== undefined
    ? `Độ tin cậy giả lập ${Math.round(Number(rawScore) * 100)}%`
    : `Cosine ${formatNumber(result.similarity, 4)} · margin ${formatNumber(result.margin, 4)}`;
  const ranking = Array.isArray(result.ranking) ? result.ranking.map((item, index) => {
    const score = Number(item.similarity);
    const bounded = Math.max(-1, Math.min(1, Number.isFinite(score) ? score : 0));
    const position = (bounded + 1) * 50;
    const segmentLeft = bounded < 0 ? position : 50;
    const segmentWidth = Math.abs(bounded) * 50;
    const direction = bounded < 0 ? "negative" : "positive";
    const rank = Number.isInteger(item.rank) ? item.rank : index + 1;
    return `<div class="identity-rank-item ${rank === 1 ? "top" : ""}">
      <span class="rank-number">${rank}</span>
      <strong>${escapeHtml(item.label)}</strong>
      <div class="score-scale ${direction}" aria-label="${escapeHtml(item.label)}: cosine ${formatNumber(score, 4)} trên thang âm 1 đến 1">
        <div class="score-scale-head"><span>Cosine</span><strong>${formatNumber(score, 4)}</strong></div>
        <div class="rank-track"><em></em><i style="left:${segmentLeft}%;width:${segmentWidth}%"></i><b style="left:${position}%"></b></div>
        <div class="score-scale-labels"><span>-1</span><span>0</span><span>1</span></div>
      </div>
    </div>`;
  }).join("") : "";
  const allLabels = ranking
    ? `<section class="identity-ranking"><div class="identity-ranking-head"><h3>Điểm của tất cả label</h3><span>${result.ranking.length} label · cao đến thấp</span></div>${ranking}</section>`
    : "";
  byId("identity-result").innerHTML = `<p class="eyebrow">Kết quả gần nhất · ${escapeHtml(result.model_backend)}</p>
    <div class="identity-answer ${unknown || rankedOnly ? "unknown" : ""}">
      <strong>${escapeHtml(answer)}</strong>
      <span>${escapeHtml(result.sample_id)}</span>
      <div class="confidence-meter"><i style="width:${width}%"></i></div>
      <span>${escapeHtml(scoreText)} · ${escapeHtml(result.reason)}</span>
      <small>Model ${escapeHtml(result.model_id)} · ${escapeHtml((result.warnings || []).length)} cảnh báo tiền xử lý</small>
    </div>${allLabels}`;
}

function renderComparison(result) {
  const ranking = result.ranking.map(item => {
    const score = Number(item.similarity);
    const bounded = Math.max(-1, Math.min(1, score));
    const position = (bounded + 1) * 50;
    const segmentLeft = bounded < 0 ? position : 50;
    const segmentWidth = Math.abs(bounded) * 50;
    const direction = bounded < 0 ? "negative" : "positive";
    return `<div class="rank-item">
      <span class="rank-number">${item.rank}</span>
      <div class="rank-identity"><strong>Mẫu ${escapeHtml(item.input_order)}</strong><code>${escapeHtml(item.candidate_id)}</code></div>
      <div class="score-scale ${direction}" aria-label="Cosine similarity ${formatNumber(score, 4)} trên thang âm 1 đến 1">
        <div class="score-scale-head"><span>Cosine similarity</span><strong>${formatNumber(score, 4)}</strong></div>
        <div class="rank-track"><em></em><i style="left:${segmentLeft}%;width:${segmentWidth}%"></i><b style="left:${position}%"></b></div>
        <div class="score-scale-labels"><span>-1</span><span>0</span><span>1</span></div>
      </div>
    </div>`;
  }).join("");
  const warnings = (result.reference_warnings || []).length + result.ranking.reduce((total, item) => total + (item.warnings || []).length, 0);
  byId("comparison-result").innerHTML = `${ranking}<div class="result-trace">Model ${escapeHtml(result.model_id)} · ${escapeHtml(result.model_backend)} · ${warnings} cảnh báo QC/tiền xử lý</div>`;
}

async function pollInference() {
  try {
    // Jobs are mutable while QUEUED/PREDICTING, so poll the bounded cache and
    // deduplicate terminal results by job_id instead of advancing past a job.
    const payload = await api("/api/inference/results?after=0");
    payload.jobs.forEach(job => {
      if (state.renderedJobs.has(job.job_id) || !["SUCCEEDED", "FAILED"].includes(job.state)) return;
      state.renderedJobs.add(job.job_id);
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
    const eligible = payload.trials.filter(item => item.status === "COMPLETE" && item.export_finalized);
    if (state.savedTrial) {
      const finalized = payload.trials.find(item => item.trial_id === state.savedTrial.trial_id);
      if (finalized) state.savedTrial = finalized;
    }
    byId("trial-options").innerHTML = eligible.map(item => `<option value="${escapeHtml(item.trial_id)}">${escapeHtml(item.name || "Chưa đặt tên")} · COMPLETE · QC ${escapeHtml(item.quality || "NOT_EVALUATED")}</option>`).join("");
    renderLibrary();
    if (state.savedTrial) renderSavedTrial();
    return payload.trials;
  } catch { return state.trials; /* Catalog may be empty while the first trial is open. */ }
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
    const complete = item.status === "COMPLETE" && item.export_finalized;
    const source = item.mode === "HARDWARE" ? "HARDWARE" : item.mode;
    return `<tr>
      <td><strong>${escapeHtml(item.name || "Chưa đặt tên")}</strong></td>
      <td><code>${escapeHtml(item.trial_id)}</code></td>
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
  byId("identity-button").addEventListener("click", async () => {
    const sampleId = byId("identity-sample").value.trim();
    const known = state.trials.find(item => item.trial_id === sampleId);
    if (known && (known.status !== "COMPLETE" || !known.export_finalized)) {
      byId("identity-result").innerHTML = '<p class="eyebrow">Không thể dự đoán</p><div class="empty-state">Mẫu này đã bị hủy hoặc chưa lưu hoàn chỉnh. Hãy chọn một mẫu có trạng thái COMPLETE.</div>';
      return;
    }
    try {
      await api("/api/inference/identity", {method: "POST", body: JSON.stringify({sample_id: sampleId})});
      byId("identity-result").innerHTML = '<p class="eyebrow">Đang xử lý</p><div class="empty-state">Job đã vào queue, đang chờ predictor.</div>';
    } catch (error) {
      const message = /Unsupported schema\/status|ABORTED/.test(error.message)
        ? "Mẫu này đã bị hủy hoặc chưa hoàn chỉnh nên không thể đưa vào model. Hãy chọn mẫu COMPLETE."
        : error.message;
      byId("identity-result").innerHTML = `<p class="eyebrow">Không thể dự đoán</p><div class="empty-state">${escapeHtml(message)}</div>`;
    }
  });
  byId("comparison-button").addEventListener("click", async () => {
    const referenceId = byId("reference-id").value.trim();
    const candidates = [...document.querySelectorAll(".candidate-input")].map(input => input.value.trim()).filter(Boolean);
    if (!referenceId) {
      byId("comparison-result").innerHTML = '<div class="empty-state">Hãy chọn mẫu tham chiếu X.</div>';
      return;
    }
    if (candidates.length < 1 || candidates.length > 4) {
      byId("comparison-result").innerHTML = '<div class="empty-state">Hãy chọn từ 1 đến 4 mẫu cần so sánh.</div>';
      return;
    }
    if (new Set(candidates).size !== candidates.length) {
      byId("comparison-result").innerHTML = '<div class="empty-state">Các mẫu so sánh đang bị trùng. Mỗi trial_id chỉ được chọn một lần.</div>';
      return;
    }
    try {
      await api("/api/inference/compare", {method: "POST", body: JSON.stringify({reference_id: referenceId, candidate_ids: candidates})});
      byId("comparison-result").innerHTML = '<div class="empty-state">Đang mã hóa và xếp hạng.</div>';
    } catch (error) {
      const message = /must be unique/.test(error.message)
        ? "Các mẫu so sánh phải khác nhau; mỗi trial_id chỉ được chọn một lần."
        : error.message;
      byId("comparison-result").innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
    }
  });
  byId("library-search").addEventListener("input", renderLibrary);
  byId("library-status").addEventListener("change", renderLibrary);
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
  pollSnapshot(); pollMessages(); pollInference(); loadTrials();
  setInterval(pollSnapshot, 1000);
  setInterval(pollMessages, 700);
  setInterval(pollInference, 700);
  setInterval(loadTrials, 2000);
  window.addEventListener("resize", () => state.snapshot && drawCharts(state.snapshot));
}

document.addEventListener("DOMContentLoaded", boot);
