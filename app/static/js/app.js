/**
 * NeerNirikshak — Pro Max Dashboard Frontend
 * IoT Water Quality Telemetry & Dual-Stage AI Epidemic Intelligence
 */

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS & PALETTE
// ═══════════════════════════════════════════════════════════════════════════════

const API = '';
const REFRESH_MS = 4_000;
const SEVERITY = ['None', 'Mild', 'Moderate', 'Severe'];

const COLORS = {
  safe: '#00f5a0',
  safeRgb: '0,245,160',
  danger: '#fb7185',
  dangerRgb: '251,113,133',
  warning: '#fbbf24',
  warningRgb: '251,191,36',
  cyan: '#00f5a0',
  cyanRgb: '0,245,160',
  blue: '#00d9f5',
  blueRgb: '0,217,245',
  purple: '#818cf8',
  purpleRgb: '129,140,248',
  text: '#94a3b8',
  grid: 'rgba(255,255,255,0.06)',
};

// ═══════════════════════════════════════════════════════════════════════════════
// CHART.JS PRO MAX DEFAULTS
// ═══════════════════════════════════════════════════════════════════════════════

Chart.defaults.color = COLORS.text;
Chart.defaults.borderColor = COLORS.grid;
Chart.defaults.font.family = "'DM Sans', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.pointStyleWidth = 8;
Chart.defaults.plugins.legend.labels.padding = 14;

// ═══════════════════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════════════════

const state = {
  mode: 'demo',
  sensorData: [],
  symptomData: [],
  liveResult: null,
  datasetStats: null,
  charts: {},
  soundEnabled: true,
};

// ═══════════════════════════════════════════════════════════════════════════════
// TELEMETRY AUDIO FX (WEB AUDIO API)
// ═══════════════════════════════════════════════════════════════════════════════

let audioCtx = null;
function playTelemetryBeep(freq = 880, type = 'sine', duration = 0.08) {
  if (!state.soundEnabled) return;
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(0.04, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
  } catch (e) {
    // Audio context may be restricted before user gesture
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

async function apiFetch(path) {
  try {
    const res = await fetch(API + path);
    const json = await res.json();
    return json.success ? json : null;
  } catch (e) {
    console.warn('API error:', path, e);
    return null;
  }
}

function formatTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + formatTime(ts);
}

function riskClass(level) {
  if (!level) return 'safe';
  const l = level.toLowerCase();
  if (l === 'high') return 'danger';
  if (l === 'watch') return 'warning';
  return 'safe';
}

function riskIcon(level) {
  const l = (level || '').toLowerCase();
  if (l === 'high') return '🚨';
  if (l === 'watch') return '⚠️';
  return '🛡️';
}

// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION & HEADER HUD
// ═══════════════════════════════════════════════════════════════════════════════

function initNav() {
  const toggle = document.getElementById('navToggle');
  const links = document.getElementById('navLinks');
  if (toggle && links) {
    toggle.addEventListener('click', () => {
      links.classList.toggle('open');
      playTelemetryBeep(640, 'triangle', 0.05);
    });

    links.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', () => {
        links.classList.remove('open');
        playTelemetryBeep(720, 'sine', 0.04);
      });
    });
  }

  // Audio Toggle
  const audioBtn = document.getElementById('audioToggle');
  const audioIcon = document.getElementById('audioIcon');
  if (audioBtn && audioIcon) {
    audioBtn.addEventListener('click', () => {
      state.soundEnabled = !state.soundEnabled;
      audioIcon.textContent = state.soundEnabled ? '🔊' : '🔇';
      audioBtn.style.opacity = state.soundEnabled ? '1' : '0.5';
      if (state.soundEnabled) playTelemetryBeep(920, 'sine', 0.08);
    });
  }

  // Active section spy
  const sections = document.querySelectorAll('section[id]');
  const observer = new IntersectionObserver(
    entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const id = entry.target.id;
          document.querySelectorAll('.nav-link').forEach(l => {
            l.classList.toggle('active', l.dataset.section === id);
          });
        }
      });
    },
    { rootMargin: '-30% 0px -60% 0px' }
  );
  sections.forEach(s => observer.observe(s));

  // Live ticking clock in footer
  const footerClock = document.getElementById('footerClock');
  if (footerClock) {
    setInterval(() => {
      footerClock.textContent = new Date().toUTCString().replace('GMT', 'UTC');
    }, 1000);
  }

  // Simulated latency jitter (38ms - 52ms)
  const latencyEl = document.getElementById('telemetryLatency');
  if (latencyEl) {
    setInterval(() => {
      const ms = Math.floor(38 + Math.random() * 16);
      latencyEl.textContent = `${ms}ms`;
    }, 3000);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// STATUS MONITORING
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchStatus() {
  const res = await apiFetch('/api/status');
  if (!res) return;

  state.mode = res.mode;
  const dot = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  const banner = document.getElementById('demoBanner');

  if (res.mode === 'live') {
    if (dot) dot.className = 'status-dot live';
    if (text) text.textContent = 'ONLINE // LIVE STREAM';
    if (banner) banner.classList.remove('visible');
  } else {
    if (dot) dot.className = 'status-dot demo';
    if (text) text.textContent = 'SIMULATION RUNNING';
    if (banner) banner.classList.add('visible');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SENSOR TELEMETRY CHARTS & TABLE
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchSensorData() {
  const res = await apiFetch('/api/sensor-data');
  if (!res) return;

  state.sensorData = res.data;
  renderSensorCharts();
  renderSensorTable();
}

function renderSensorCharts() {
  const data = state.sensorData;
  if (!data.length) return;

  const labels = data.map(d => formatTime(d.timestamp));
  const tdsMax = data.map(d => {
    const raw = d.tds_max !== undefined ? d.tds_max : (d.tds || 0);
    return Number(raw).toFixed(1);
  });
  const turbidity = data.map(d => Number(d.turbidity || 0).toFixed(1));

  // TDS Line Chart
  if (state.charts.tds) {
    state.charts.tds.data.labels = labels;
    state.charts.tds.data.datasets[0].data = tdsMax;
    state.charts.tds.update('none');
  } else {
    const ctx = document.getElementById('tdsChart');
    if (ctx) {
      state.charts.tds = new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Peak Conductivity / TDS (mg/L)',
              data: tdsMax,
              borderColor: COLORS.cyan,
              backgroundColor: `rgba(${COLORS.cyanRgb},0.12)`,
              fill: true,
              tension: 0.35,
              borderWidth: 2.2,
              pointRadius: 2.5,
              pointHoverRadius: 6,
              pointBackgroundColor: COLORS.cyan,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'top' } },
          scales: {
            y: { title: { display: true, text: 'TDS (mg/L)' }, grid: { color: COLORS.grid } },
            x: { grid: { display: false } },
          },
        },
      });
    }
  }

  // Turbidity Line Chart
  if (state.charts.turbidity) {
    state.charts.turbidity.data.labels = labels;
    state.charts.turbidity.data.datasets[0].data = turbidity;
    state.charts.turbidity.update('none');
  } else {
    const ctx = document.getElementById('turbidityChart');
    if (ctx) {
      state.charts.turbidity = new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'Turbidity (NTU)',
              data: turbidity,
              borderColor: COLORS.warning,
              backgroundColor: `rgba(${COLORS.warningRgb},0.12)`,
              fill: true,
              tension: 0.35,
              borderWidth: 2.2,
              pointRadius: 2.5,
              pointHoverRadius: 6,
              pointBackgroundColor: COLORS.warning,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'top' } },
          scales: {
            y: { title: { display: true, text: 'NTU' }, grid: { color: COLORS.grid } },
            x: { grid: { display: false } },
          },
        },
      });
    }
  }
}

function renderSensorTable() {
  const tbody = document.getElementById('sensorTableBody');
  if (!tbody) return;
  const data = state.sensorData.slice().reverse().slice(0, 10);

  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="table-empty-row">No telemetry packets received</td></tr>';
    return;
  }

  tbody.innerHTML = data
    .map(d => {
      const potable = d.potable === 1;
      const cls = potable ? 'safe' : 'danger';
      const label = potable ? 'Potable' : 'Risk Flagged';
      const rawTds = d.tds_max !== undefined ? d.tds_max : (d.tds || 0);
      return `<tr>
        <td>${formatDate(d.timestamp)}</td>
        <td><span style="color:var(--neon-cyan);">${d.device_id || 'ESP32-NODE'}</span></td>
        <td>${Number(rawTds).toFixed(1)}</td>
        <td>${Number(d.tds_min || 0).toFixed(1)}</td>
        <td>${Number(d.turbidity || 0).toFixed(1)}</td>
        <td><span class="status-badge ${cls}">${label}</span></td>
      </tr>`;
    })
    .join('');
}

// ═══════════════════════════════════════════════════════════════════════════════
// SYMPTOM SURVEILLANCE CHARTS & TABLE
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchSymptomData() {
  const res = await apiFetch('/api/symptom-data');
  if (!res) return;

  state.symptomData = res.data;
  renderSymptomCharts();
  renderSymptomTable();
}

function renderSymptomCharts() {
  const data = state.symptomData;
  if (!data.length) return;

  const keys = ['nausea', 'fever', 'dehydration', 'abdominal_cramps', 'diarrhoea'];
  const labels = ['Nausea', 'Fever', 'Dehydration', 'Abdominal Cramps', 'Diarrhoea'];
  const avgs = keys.map(k => {
    const vals = data.map(d => d[k] || 0);
    return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
  });

  // Bar chart
  if (state.charts.symptomBar) {
    state.charts.symptomBar.data.datasets[0].data = avgs;
    state.charts.symptomBar.update('none');
  } else {
    const ctx = document.getElementById('symptomBarChart');
    if (ctx) {
      state.charts.symptomBar = new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: 'Average Severity (0-3)',
              data: avgs,
              backgroundColor: [
                `rgba(${COLORS.cyanRgb},0.65)`,
                `rgba(${COLORS.blueRgb},0.65)`,
                `rgba(${COLORS.warningRgb},0.65)`,
                `rgba(${COLORS.purpleRgb},0.65)`,
                `rgba(${COLORS.dangerRgb},0.65)`,
              ],
              borderColor: [COLORS.cyan, COLORS.blue, COLORS.warning, COLORS.purple, COLORS.danger],
              borderWidth: 1.5,
              borderRadius: 6,
              barPercentage: 0.65,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: {
              beginAtZero: true,
              max: 3,
              title: { display: true, text: 'Mean Clinical Score' },
              grid: { color: COLORS.grid },
            },
            x: { grid: { display: false } },
          },
        },
      });
    }
  }

  // Radar chart
  if (state.charts.symptomRadar) {
    state.charts.symptomRadar.data.datasets[0].data = avgs;
    state.charts.symptomRadar.update('none');
  } else {
    const ctx = document.getElementById('symptomRadarChart');
    if (ctx) {
      state.charts.symptomRadar = new Chart(ctx, {
        type: 'radar',
        data: {
          labels,
          datasets: [
            {
              label: 'Symptom Vector',
              data: avgs,
              borderColor: COLORS.cyan,
              backgroundColor: `rgba(${COLORS.cyanRgb},0.2)`,
              borderWidth: 2,
              pointBackgroundColor: COLORS.cyan,
              pointRadius: 4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            r: {
              beginAtZero: true,
              max: 3,
              ticks: { stepSize: 1, color: COLORS.text, backdropColor: 'transparent' },
              grid: { color: COLORS.grid },
              angleLines: { color: COLORS.grid },
              pointLabels: { color: COLORS.text, font: { size: 11, family: 'Plus Jakarta Sans' } },
            },
          },
        },
      });
    }
  }
}

function renderSymptomTable() {
  const tbody = document.getElementById('symptomTableBody');
  if (!tbody) return;
  const data = state.symptomData.slice(0, 10);

  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="table-empty-row">No clinical records found</td></tr>';
    return;
  }

  tbody.innerHTML = data
    .map(d => {
      const score = (d.nausea || 0) + (d.fever || 0) + (d.dehydration || 0) + (d.abdominal_cramps || 0) + (d.diarrhoea || 0);
      const renderSev = v => `<span class="severity-dot severity-${v}"></span> ${SEVERITY[v] || v}`;
      return `<tr>
        <td>${formatDate(d.timestamp)}</td>
        <td><strong style="color:var(--neon-cyan);">${d.location || 'Nerul'}</strong></td>
        <td>${renderSev(d.nausea || 0)}</td>
        <td>${renderSev(d.fever || 0)}</td>
        <td>${renderSev(d.dehydration || 0)}</td>
        <td>${renderSev(d.abdominal_cramps || 0)}</td>
        <td>${renderSev(d.diarrhoea || 0)}</td>
        <td><strong style="color:${score > 6 ? COLORS.danger : COLORS.safe};">${score}/15</strong></td>
      </tr>`;
    })
    .join('');
}

// ═══════════════════════════════════════════════════════════════════════════════
// LIVE INFERENCE & PHYSICAL HYDRO-CHAMBER VISUALIZER
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchLivePrediction() {
  const res = await apiFetch('/api/predict/live');
  if (!res) return;

  state.liveResult = res;
  updateDashboardMetrics(res);
}

function updateDashboardMetrics(res) {
  const d = res.data;
  if (!d) return;

  const sensor = res.sensor_source || {};
  const rawTds = sensor.tds !== undefined && sensor.tds !== null ? sensor.tds : sensor.tds_max;
  const tdsDisplay = rawTds !== undefined && rawTds !== null ? Number(rawTds).toFixed(1) : '—';
  const turbDisplay = sensor.turbidity !== undefined && sensor.turbidity !== null ? Number(sensor.turbidity).toFixed(1) : '—';
  const cls = riskClass(d.outbreak.risk_level);

  // 1. Metric Cards
  const tdsValEl = document.getElementById('tdsValue');
  const tdsSubEl = document.getElementById('tdsSub');
  const turbValEl = document.getElementById('turbidityValue');
  const potValEl = document.getElementById('potabilityValue');
  const potSubEl = document.getElementById('potabilitySub');
  const outValEl = document.getElementById('outbreakValue');
  const outSubEl = document.getElementById('outbreakSub');

  if (tdsValEl) tdsValEl.textContent = tdsDisplay;
  if (tdsSubEl) tdsSubEl.textContent = sensor.turb_voltage !== undefined ? `Sensor: ${sensor.turb_voltage} V` : (rawTds !== undefined ? `≈ ${rawTds} mg/L` : '—');
  if (turbValEl) turbValEl.textContent = turbDisplay;

  if (potValEl) potValEl.textContent = d.potability.label;
  if (potSubEl) potSubEl.textContent = `${d.potability.confidence}% confidence`;
  const potCard = document.getElementById('metricPotability');
  if (potCard) potCard.className = `bento-cell metric-card glass-card ${d.potability.is_potable ? 'safe' : 'danger'}`;

  if (outValEl) outValEl.textContent = `${d.outbreak.probability}%`;
  if (outSubEl) outSubEl.textContent = `${d.outbreak.risk_level} Risk Level`;
  const outCard = document.getElementById('metricOutbreak');
  if (outCard) outCard.className = `bento-cell metric-card glass-card ${cls}`;

  // 2. Outbreak Master Badge
  const badge = document.getElementById('outbreakBadge');
  if (badge) {
    badge.className = `master-outbreak-card ${cls}`;
    const badgeIcon = document.getElementById('badgeIcon');
    const badgeLevel = document.getElementById('badgeLevel');
    const badgeProb = document.getElementById('badgeProb');
    const badgeSub = document.getElementById('badgeSubStatus');

    if (badgeIcon) badgeIcon.textContent = riskIcon(d.outbreak.risk_level);
    if (badgeLevel) badgeLevel.textContent = `${d.outbreak.risk_level.toUpperCase()} THREAT`;
    if (badgeProb) badgeProb.textContent = `${d.outbreak.probability}% Epidemic Probability`;
    if (badgeSub) badgeSub.textContent = d.outbreak.risk_level === 'High' ? 'Urgent boil water notice required' : (d.outbreak.risk_level === 'Watch' ? 'Elevated symptoms in Nerul ward' : 'Normal potable baseline verified');
  }

  // 3. Physical Hydro-Chamber Visualizer
  const fluid = document.getElementById('fluidBody');
  const turbPart = document.getElementById('turbidityParticulates');
  const chamberStatusTag = document.getElementById('chamberStatusTag');
  const chamberStatusText = document.getElementById('chamberStatusText');
  const sensorVoltageValue = document.getElementById('sensorVoltageValue');
  const voltageBar = document.getElementById('voltageBar');
  const tdsDensityValue = document.getElementById('tdsDensityValue');
  const tdsBar = document.getElementById('tdsBar');
  const streamTimestamp = document.getElementById('streamTimestamp');

  const turbNum = parseFloat(turbDisplay) || 0;
  const tdsNum = parseFloat(tdsDisplay) || 0;

  if (fluid) {
    if (turbNum > 15) {
      // Murky amber/silt contamination tint
      fluid.style.background = 'linear-gradient(180deg, rgba(245, 158, 11, 0.6) 0%, rgba(120, 53, 15, 0.85) 100%)';
    } else if (turbNum > 5) {
      fluid.style.background = 'linear-gradient(180deg, rgba(56, 189, 248, 0.5) 0%, rgba(20, 83, 126, 0.8) 100%)';
    } else {
      // Pure crystal cyan
      fluid.style.background = 'linear-gradient(180deg, rgba(0, 242, 254, 0.45) 0%, rgba(14, 116, 144, 0.8) 100%)';
    }
  }

  if (chamberStatusText) {
    if (turbNum > 15) chamberStatusText.textContent = 'SAMPLE OPTICAL: HIGH TURBIDITY';
    else if (turbNum > 5) chamberStatusText.textContent = 'SAMPLE OPTICAL: SLIGHT HAZE';
    else chamberStatusText.textContent = 'SAMPLE OPTICAL: PURE CLEAR';
  }

  if (sensorVoltageValue) {
    const v = sensor.turb_voltage !== undefined ? sensor.turb_voltage : '4.12';
    sensorVoltageValue.textContent = `${v} V`;
    if (voltageBar) {
      const pct = Math.min(100, Math.max(10, (parseFloat(v) / 5) * 100));
      voltageBar.style.width = `${pct}%`;
    }
  }

  if (tdsDensityValue) {
    tdsDensityValue.textContent = `${tdsNum.toFixed(1)} mg/L`;
    if (tdsBar) {
      const tdsPct = Math.min(100, Math.max(5, (tdsNum / 1000) * 100));
      tdsBar.style.width = `${tdsPct}%`;
    }
  }

  if (streamTimestamp) {
    streamTimestamp.textContent = formatTime(sensor.timestamp || new Date());
  }

  // 4. Update Pipeline Nodes
  const pipePotResult = document.getElementById('pipePotResult');
  const pipeOutbreakResult = document.getElementById('pipeOutbreakResult');
  if (pipePotResult) {
    pipePotResult.textContent = `${d.potability.label} (${d.potability.confidence}%)`;
    pipePotResult.style.color = d.potability.is_potable ? COLORS.safe : COLORS.danger;
  }
  if (pipeOutbreakResult) {
    pipeOutbreakResult.textContent = `${d.outbreak.risk_level} Risk (${d.outbreak.probability}%)`;
    pipeOutbreakResult.style.color = d.outbreak.risk_color;
  }

  // 5. Gauge & Risk Advice
  drawGauge(d.outbreak.probability, d.outbreak.risk_color);
  const riskLabel = document.getElementById('riskLabel');
  const riskAdvice = document.getElementById('riskAdvice');
  if (riskLabel) {
    riskLabel.textContent = `${d.outbreak.risk_level.toUpperCase()} RISK — ${d.outbreak.probability}%`;
    riskLabel.style.color = d.outbreak.risk_color;
  }
  if (riskAdvice) riskAdvice.textContent = d.outbreak.advice;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SVG GAUGE
// ═══════════════════════════════════════════════════════════════════════════════

function drawGauge(value, color) {
  const container = document.getElementById('gaugeContainer');
  if (!container) return;
  const w = 280, h = 160;
  const cx = w / 2, cy = h - 14;
  const radius = 105;
  const startAngle = Math.PI;
  const endAngle = 2 * Math.PI;
  const valueAngle = startAngle + (value / 100) * (endAngle - startAngle);

  const px = (a, r) => cx + r * Math.cos(a);
  const py = (a, r) => cy + r * Math.sin(a);

  const arc = (start, end, r) => {
    const largeArc = end - start > Math.PI ? 1 : 0;
    return `M ${px(start, r)} ${py(start, r)} A ${r} ${r} 0 ${largeArc} 1 ${px(end, r)} ${py(end, r)}`;
  };

  const seg1End = startAngle + (0.35 * Math.PI);
  const seg2End = startAngle + (0.65 * Math.PI);

  let svg = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">`;

  // Track segments
  svg += `<path d="${arc(startAngle, seg1End, radius)}" fill="none" stroke="rgba(16,185,129,0.2)" stroke-width="14" stroke-linecap="round"/>`;
  svg += `<path d="${arc(seg1End, seg2End, radius)}" fill="none" stroke="rgba(245,158,11,0.2)" stroke-width="14"/>`;
  svg += `<path d="${arc(seg2End, endAngle, radius)}" fill="none" stroke="rgba(239,68,68,0.2)" stroke-width="14" stroke-linecap="round"/>`;

  // Value arc
  const clampedAngle = Math.min(valueAngle, endAngle);
  if (value > 0) {
    svg += `<path d="${arc(startAngle, clampedAngle, radius)}" fill="none" stroke="${color}" stroke-width="14" stroke-linecap="round" filter="drop-shadow(0 0 10px ${color}60)"/>`;
  }

  // Needle
  const needleLen = radius - 24;
  const nx = px(clampedAngle, needleLen);
  const ny = py(clampedAngle, needleLen);
  svg += `<line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="${color}" stroke-width="3" stroke-linecap="round"/>`;
  svg += `<circle cx="${cx}" cy="${cy}" r="7" fill="${color}" filter="drop-shadow(0 0 8px ${color}80)"/>`;
  svg += `<circle cx="${cx}" cy="${cy}" r="3.5" fill="#030712"/>`;

  // Numerical Text
  svg += `<text x="${cx}" y="${cy - 24}" text-anchor="middle" fill="${color}" font-size="34" font-weight="800" font-family="Space Grotesk">${value.toFixed(1)}%</text>`;

  svg += '</svg>';
  container.innerHTML = svg;
}

// ═══════════════════════════════════════════════════════════════════════════════
// WHAT-IF ANALYSIS & PRESETS
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchWhatIf() {
  const res = await apiFetch('/api/whatif');
  if (!res || !res.data) return;

  const grid = document.getElementById('whatifGrid');
  if (!grid) return;
  const scenarios = [
    { key: 'current', title: 'Current Stream', icon: '📍' },
    { key: 'clean_water', title: 'Filtered Baseline', icon: '💧' },
    { key: 'no_symptoms', title: 'Zero Clinical Cases', icon: '😊' },
    { key: 'worst_case', title: 'Monsoon Hazard Spike', icon: '💀' },
  ];

  grid.innerHTML = scenarios
    .map(s => {
      const d = res.data[s.key];
      if (!d) return '';
      const prob = d.outbreak.probability;
      const cls = riskClass(d.outbreak.risk_level);
      return `<div class="whatif-card">
        <div class="whatif-title">${s.icon} ${s.title}</div>
        <div class="whatif-value" style="color:${d.outbreak.risk_color}">${prob}%</div>
        <div class="whatif-level" style="color:${d.outbreak.risk_color}">${d.outbreak.risk_level.toUpperCase()} RISK</div>
      </div>`;
    })
    .join('');
}

// Global function to trigger presets from chips
window.applyPreset = function(type) {
  playTelemetryBeep(780, 'sine', 0.06);

  const presets = {
    clean: { tdsMax: 80, tdsMin: 30, turb: 0.8, n: 0, f: 0, d: 0, c: 0, dia: 0 },
    monsoon: { tdsMax: 650, tdsMin: 320, turb: 28.5, n: 1, f: 2, d: 1, c: 2, dia: 2 },
    cholera: { tdsMax: 820, tdsMin: 410, turb: 34.0, n: 2, f: 2, d: 3, c: 3, dia: 3 },
    industrial: { tdsMax: 2400, tdsMin: 1200, turb: 14.0, n: 2, f: 0, d: 1, c: 1, dia: 1 },
  };

  const p = presets[type];
  if (!p) return;

  const setVal = (id, valId, val, isSev = false) => {
    const input = document.getElementById(id);
    const label = document.getElementById(valId);
    if (input) input.value = val;
    if (label) label.textContent = isSev ? SEVERITY[val] : val;
  };

  setVal('inputTdsMax', 'valTdsMax', p.tdsMax);
  setVal('inputTdsMin', 'valTdsMin', p.tdsMin);
  setVal('inputTurbidity', 'valTurbidity', p.turb);
  setVal('inputNausea', 'valNausea', p.n, true);
  setVal('inputFever', 'valFever', p.f, true);
  setVal('inputDehydration', 'valDehydration', p.d, true);
  setVal('inputCramps', 'valCramps', p.c, true);
  setVal('inputDiarrhoea', 'valDiarrhoea', p.dia, true);

  // Auto trigger prediction
  const btn = document.getElementById('btnPredict');
  if (btn) btn.click();
};

// ═══════════════════════════════════════════════════════════════════════════════
// DATASET STATS & FEATURE IMPORTANCE
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchDatasetStats() {
  const res = await apiFetch('/api/dataset-stats');
  if (!res || !res.data) return;

  state.datasetStats = res.data;
  const d = res.data;

  // Stats cards
  const statSamples = document.getElementById('statSamples');
  const statPotable = document.getElementById('statPotable');
  const statReports = document.getElementById('statReports');
  const statOutbreak = document.getElementById('statOutbreak');

  if (statSamples && d.water) statSamples.textContent = d.water.total_samples.toLocaleString();
  if (statPotable && d.water) statPotable.textContent = d.water.potable_pct + '%';
  if (statReports && d.symptoms) statReports.textContent = d.symptoms.total_reports.toLocaleString();
  if (statOutbreak && d.symptoms) statOutbreak.textContent = d.symptoms.outbreak_pct + '%';

  // Feature Importance Charts
  if (d.outbreak_importance) {
    renderImportanceChart(
      'importanceChart',
      d.outbreak_importance.map(f => f.feature),
      d.outbreak_importance.map(f => f.importance),
      COLORS.cyan
    );
  }

  if (d.potability_importance) {
    renderImportanceChart(
      'potabilityImportanceChart',
      d.potability_importance.map(f => f.feature),
      d.potability_importance.map(f => f.importance),
      COLORS.blue
    );
  }

  if (d.symptoms && d.symptoms.outbreak_vs_no) {
    renderOutbreakCompareChart(d.symptoms.outbreak_vs_no);
  }
}

function renderImportanceChart(id, labels, values, color) {
  const ctx = document.getElementById(id);
  if (!ctx) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels.map(l => l.replace(/_/g, ' ').toUpperCase()),
      datasets: [
        {
          label: 'Gini Importance Score',
          data: values,
          backgroundColor: color,
          borderRadius: 6,
          barPercentage: 0.6,
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, grid: { color: COLORS.grid } },
        y: { grid: { display: false }, ticks: { font: { size: 10, family: 'JetBrains Mono' } } },
      },
    },
  });
}

function renderOutbreakCompareChart(data) {
  const ctx = document.getElementById('outbreakCompareChart');
  if (!ctx) return;

  const labels = Object.keys(data.outbreak || {}).map(l => l.replace(/_/g, ' ').toUpperCase());
  const outVals = Object.values(data.outbreak || {});
  const noVals = Object.values(data.no_outbreak || {});

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Outbreak Phase',
          data: outVals,
          backgroundColor: `rgba(${COLORS.dangerRgb},0.75)`,
          borderRadius: 6,
        },
        {
          label: 'Non-Outbreak Phase',
          data: noVals,
          backgroundColor: `rgba(${COLORS.safeRgb},0.75)`,
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'top' } },
      scales: {
        y: { beginAtZero: true, max: 3, grid: { color: COLORS.grid } },
        x: { grid: { display: false } },
      },
    },
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// MANUAL SIMULATOR FORM
// ═══════════════════════════════════════════════════════════════════════════════

function initPredictForm() {
  const waterSliders = [
    { id: 'inputTdsMax', valId: 'valTdsMax', type: 'number' },
    { id: 'inputTdsMin', valId: 'valTdsMin', type: 'number' },
    { id: 'inputTurbidity', valId: 'valTurbidity', type: 'number' },
  ];

  const symptomSliders = [
    { id: 'inputNausea', valId: 'valNausea', type: 'severity' },
    { id: 'inputFever', valId: 'valFever', type: 'severity' },
    { id: 'inputDehydration', valId: 'valDehydration', type: 'severity' },
    { id: 'inputCramps', valId: 'valCramps', type: 'severity' },
    { id: 'inputDiarrhoea', valId: 'valDiarrhoea', type: 'severity' },
  ];

  const allSliders = [...waterSliders, ...symptomSliders];

  allSliders.forEach(s => {
    const slider = document.getElementById(s.id);
    const valEl = document.getElementById(s.valId);
    if (!slider || !valEl) return;

    slider.addEventListener('input', () => {
      if (s.type === 'severity') {
        valEl.textContent = SEVERITY[parseInt(slider.value)];
      } else {
        valEl.textContent = slider.value;
      }
    });
  });

  const btn = document.getElementById('btnPredict');
  if (btn) {
    btn.addEventListener('click', async () => {
      playTelemetryBeep(1040, 'triangle', 0.08);
      btn.style.opacity = '0.7';
      btn.textContent = '⏳ COMPUTING INFERENCE…';

      const body = {
        tds_max: parseFloat(document.getElementById('inputTdsMax').value),
        tds_min: parseFloat(document.getElementById('inputTdsMin').value),
        turbidity: parseFloat(document.getElementById('inputTurbidity').value),
        nausea: parseInt(document.getElementById('inputNausea').value),
        fever: parseInt(document.getElementById('inputFever').value),
        dehydration: parseInt(document.getElementById('inputDehydration').value),
        abdominal_cramps: parseInt(document.getElementById('inputCramps').value),
        diarrhoea: parseInt(document.getElementById('inputDiarrhoea').value),
      };

      try {
        const res = await fetch(API + '/api/predict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const json = await res.json();

        if (json.success) {
          renderPredictResult(json.data);
        } else {
          renderPredictError(json.error || 'Prediction failed');
        }
      } catch (e) {
        renderPredictError(e.message);
      } finally {
        btn.style.opacity = '1';
        btn.innerHTML = '<span class="btn-icon">⚡</span><span>RUN PREDICTIVE INFERENCE</span>';
      }
    });
  }
}

function renderPredictResult(d) {
  const container = document.getElementById('predictResult');
  if (!container) return;
  const cls = riskClass(d.outbreak.risk_level);
  const icon = riskIcon(d.outbreak.risk_level);

  container.innerHTML = `
    <div class="result-header">
      <div style="font-size:2.8rem;margin-bottom:8px;">${icon}</div>
      <div class="result-badge ${cls}">${d.outbreak.risk_level.toUpperCase()} THREAT — ${d.outbreak.probability}%</div>
      <p style="font-size:0.88rem;color:var(--text-secondary);margin-top:6px;">${d.outbreak.advice}</p>
    </div>
    <div class="result-breakdown-list">
      <div class="breakdown-item">
        <span style="color:var(--text-muted);">STAGE 1 POTABILITY:</span>
        <strong style="color:${d.potability.is_potable ? COLORS.safe : COLORS.danger};">${d.potability.label} (${d.potability.confidence}%)</strong>
      </div>
      <div class="breakdown-item">
        <span style="color:var(--text-muted);">PEAK CONDUCTIVITY / TDS:</span>
        <strong style="color:var(--neon-cyan);">${d.inputs.tds_max_mg_l} mg/L</strong>
      </div>
      <div class="breakdown-item">
        <span style="color:var(--text-muted);">COMMUNITY SYMPTOM LOAD:</span>
        <strong style="color:var(--neon-warning);">${d.inputs.symptom_load} / 15</strong>
      </div>
    </div>
  `;
}

function renderPredictError(msg) {
  const container = document.getElementById('predictResult');
  if (!container) return;
  container.innerHTML = `
    <div style="text-align:center;padding:30px;">
      <div style="font-size:2.5rem;margin-bottom:10px;">❌</div>
      <h3 style="color:var(--neon-danger);">Inference Failed</h3>
      <p style="color:var(--text-muted);font-size:0.85rem;margin-top:6px;">${msg}</p>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════════════════════

async function init() {
  initNav();
  initPredictForm();
  drawGauge(0, COLORS.text);

  await Promise.all([
    fetchStatus(),
    fetchSensorData(),
    fetchSymptomData(),
    fetchLivePrediction(),
    fetchDatasetStats(),
    fetchWhatIf(),
  ]);

  setInterval(async () => {
    await Promise.all([
      fetchStatus(),
      fetchSensorData(),
      fetchSymptomData(),
      fetchLivePrediction(),
    ]);
  }, REFRESH_MS);
}

document.addEventListener('DOMContentLoaded', init);
