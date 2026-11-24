const LANG_NAMES = {
  en: "English",
  tr: "Türkçe",
  de: "Deutsch",
  es: "Español",
};

const state = {
  data: null,
  dict: {},
  lang: "en",
  ws: null,
  wsConnected: false,
  audioCtx: null,
  activeTab: "home",
  wizardShown: false,
  wizardStep: 0,
  devicesLoaded: false,
  devices: { cameras: [], microphones: [] },
  wizardAnswers: {
    abilities: [],
    support_needs: [],
    equipment: ["webcam", "keyboard_mouse"],
    game_genre: "action_gta",
  },
  wizardResult: null,
  signals: {
    head_yaw: 0,
    head_pitch: 0,
    gaze_x: 0,
    gaze_y: 0,
    wink_left: 0,
    wink_right: 0,
    mouth_open: 0,
    mouth_pucker: 0,
    cheek_puff: 0,
    mouth_left: 0,
    mouth_right: 0,
    eyebrow_raise: 0,
    audio_level: 0,
  },
  channelThresholds: {
    wink_left: 0.45,
    wink_right: 0.45,
    mouth_open: 0.50,
    mouth_pucker: 0.55,
    cheek_puff: 0.55,
    eyebrow_raise: 0.60,
    audio_level: 0.45,
  },
};

function t(key, params = null) {
  let val = state.dict[key];
  if (val === undefined || val === null) return key;
  if (Array.isArray(val)) return val;
  let str = String(val);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      str = str.replaceAll(`{${k}}`, String(v));
    });
  }
  return str;
}

function getWizardSteps() {
  const opt = (id) => ({
    id,
    title: t(`wizard.opt.${id}.title`),
    desc: t(`wizard.opt.${id}.desc`),
  });
  return [
    {
      key: "__lang__",
      multi: false,
      question: t("wizard.q_lang"),
      options: [
        { id: "en", title: "English", desc: "English" },
        { id: "tr", title: "Türkçe", desc: "Turkish" },
        { id: "de", title: "Deutsch", desc: "German" },
        { id: "es", title: "Español", desc: "Spanish" },
      ],
    },
    {
      key: "abilities",
      multi: true,
      question: t("wizard.q_abilities"),
      options: ["head_face", "eye_only", "one_hand", "single_switch", "sound_breath"].map(opt),
    },
    {
      key: "support_needs",
      multi: true,
      question: t("wizard.q_support"),
      options: ["high_contrast", "large_text", "tts_screenreader", "nonverbal", "glasses_no_wink"].map(opt),
    },
    {
      key: "equipment",
      multi: true,
      question: t("wizard.q_equipment"),
      options: ["webcam", "microphone", "keyboard_mouse", "gamepad"].map(opt),
    },
    {
      key: "game_genre",
      multi: false,
      question: t("wizard.q_genre"),
      options: ["action_gta", "racing", "strategy", "casual"].map(opt),
    },
  ];
}

const el = {
  srLive: document.getElementById("sr-live"),
  wsStatus: document.getElementById("ws-status"),
  langSelect: document.getElementById("lang-select"),
  setLangSelect: document.getElementById("set-lang-select"),
  voiceStatusMsg: document.getElementById("voice-status-msg"),
  activeProfileName: document.getElementById("active-profile-name"),
  activeProfileDesc: document.getElementById("active-profile-desc"),
  modeHint: document.getElementById("mode-hint"),
  homeControlsGrid: document.getElementById("home-controls-grid"),
  scannerSection: document.getElementById("scanner-section"),
  scannerTiles: document.getElementById("scanner-tiles"),
  btnBigSwitch: document.getElementById("btn-big-switch"),
  profilesGrid: document.getElementById("profiles-grid"),
  diagList: document.getElementById("diag-list"),
  btnRunDiag: document.getElementById("btn-run-diag"),
  outputLog: document.getElementById("output-log"),
  btnMode: document.getElementById("btn-mode"),
  btnQuickCam: document.getElementById("btn-quick-cam"),
  btnQuickMic: document.getElementById("btn-quick-mic"),
  btnGotoCalibrate: document.getElementById("btn-goto-calibrate"),
  btnCalCamToggle: document.getElementById("btn-cal-cam-toggle"),
  cameraStreamImg: document.getElementById("camera-stream-img"),
  cameraPlaceholder: document.getElementById("camera-placeholder"),
  camTelemetry: document.getElementById("cam-telemetry"),
  selCamera: document.getElementById("sel-camera"),
  btnRefreshDevices: document.getElementById("btn-refresh-devices"),
  chkLowLight: document.getElementById("chk-low-light"),
  reticleDot: document.getElementById("reticle-dot"),
  reticleDeadzone: document.getElementById("reticle-deadzone"),
  btnCalibrate: document.getElementById("btn-calibrate"),
  btnCalibrateReset: document.getElementById("btn-calibrate-reset"),
  slSensitivity: document.getElementById("sl-sensitivity"),
  lblSensitivity: document.getElementById("lbl-sensitivity"),
  slDeadzone: document.getElementById("sl-deadzone"),
  lblDeadzone: document.getElementById("lbl-deadzone"),
  slSmoothing: document.getElementById("sl-smoothing"),
  lblSmoothing: document.getElementById("lbl-smoothing"),
  chkSwapEyes: document.getElementById("chk-swap-eyes"),
  chkInvertX: document.getElementById("chk-invert-x"),
  chkInvertY: document.getElementById("chk-invert-y"),
  selMic: document.getElementById("sel-mic"),
  btnCalMicToggle: document.getElementById("btn-cal-mic-toggle"),
  btnMicNoiseCal: document.getElementById("btn-mic-noise-cal"),
  slMicGain: document.getElementById("sl-mic-gain"),
  lblMicGain: document.getElementById("lbl-mic-gain"),
  chkMicNoise: document.getElementById("chk-mic-noise"),
  chkMicAgc: document.getElementById("chk-mic-agc"),
  micTelemetry: document.getElementById("mic-telemetry"),
  btnContrast: document.getElementById("btn-contrast"),
  btnLargeText: document.getElementById("btn-large-text"),
  btnTts: document.getElementById("btn-tts"),
  btnOpenWizard: document.getElementById("btn-open-wizard"),
  btnEmergency: document.getElementById("btn-emergency"),
  wizardBackdrop: document.getElementById("wizard-backdrop"),
  wizardStepTag: document.getElementById("wizard-step-tag"),
  wizardTitle: document.getElementById("wizard-title"),
  wizardQuestion: document.getElementById("wizard-question"),
  wizardBody: document.getElementById("wizard-body"),
  btnWizardClose: document.getElementById("btn-wizard-close"),
  btnWizardPrev: document.getElementById("btn-wizard-prev"),
  btnWizardNext: document.getElementById("btn-wizard-next"),
};

function switchTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.tab === tabName));
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    p.classList.toggle("hidden", p.id !== `tab-${tabName}`);
  });
  if (tabName === "calibrate" && !state.devicesLoaded) {
    refreshDevices().catch(() => {});
  }
}

function playTone(freq = 500, durationMs = 60) {
  if (!state.data?.settings?.audio_cues) return;
  try {
    if (!state.audioCtx) state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = state.audioCtx.createOscillator();
    const gain = state.audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.value = 0.06;
    osc.connect(gain);
    gain.connect(state.audioCtx.destination);
    osc.start();
    setTimeout(() => osc.stop(), durationMs);
  } catch (_) {}
}

function announce(text, speakViaBackend = false) {
  if (!text) return;
  el.srLive.textContent = "";
  setTimeout(() => { el.srLive.textContent = text; }, 30);
  if (speakViaBackend && state.data?.settings?.tts_enabled) {
    apiPost("/api/speak", { text }).catch(() => {});
  }
}

async function apiGet(url) {
  const res = await fetch(url);
  return res.json();
}

async function apiPost(url, body = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function fetchLocale(lang) {
  const dict = await apiGet(`/api/i18n/${lang}`);
  state.dict = dict;
  state.lang = lang;
}

function applyTranslations() {
  document.documentElement.lang = state.lang;
  if (el.langSelect) el.langSelect.value = state.lang;
  if (el.setLangSelect) el.setLangSelect.value = state.lang;

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (key) node.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
    const key = node.getAttribute("data-i18n-aria");
    if (key) node.setAttribute("aria-label", t(key));
  });
  document.querySelectorAll("[data-i18n-alt]").forEach((node) => {
    const key = node.getAttribute("data-i18n-alt");
    if (key) node.setAttribute("alt", t(key));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((node) => {
    const key = node.getAttribute("data-i18n-title");
    if (key) node.setAttribute("title", t(key));
  });

  el.wsStatus.textContent = state.wsConnected ? t("home.status_ready") : t("home.status_connecting");
  populateDeviceSelects();
  if (state.data?.active_profile) {
    syncChannelThresholds(state.data.active_profile);
    renderTelemetry(state.data.telemetry, state.data.inputs || []);
  }
}

async function setLanguage(lang) {
  await fetchLocale(lang);
  applyTranslations();
  if (state.data?.settings) {
    const updated = await apiPost("/api/settings", { ...state.data.settings, language: lang });
    renderAll(updated);
  } else if (!el.wizardBackdrop.classList.contains("hidden")) {
    renderWizardStep(false);
  }
}

function updateSignalVisuals(channel, value) {
  state.signals[channel] = value;

  const useGaze = state.data?.active_profile?.id === "eye_gaze_action";
  const xVal = useGaze ? state.signals.gaze_x : state.signals.head_yaw;
  const yVal = useGaze ? state.signals.gaze_y : state.signals.head_pitch;
  const px = 50 + Math.max(-1, Math.min(1, xVal)) * 45;
  const py = 50 + Math.max(-1, Math.min(1, yVal)) * 45;
  el.reticleDot.style.left = `${px}%`;
  el.reticleDot.style.top = `${py}%`;

  const bar = document.getElementById(`bar-${channel}`);
  const valLbl = document.getElementById(`val-${channel}`);
  if (bar && valLbl) {
    const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
    bar.style.width = `${pct}%`;
    valLbl.textContent = `${pct}%`;
  }
}

function updateDeviceButtons(inputs) {
  const cam = inputs.find((i) => i.name === "face_tracker");
  const mic = inputs.find((i) => i.name === "audio_trigger");

  const camRunning = !!cam?.running;
  const camAvail = !!cam?.available;
  [el.btnQuickCam, el.btnCalCamToggle].forEach((btn) => {
    btn.disabled = !camAvail;
    btn.textContent = camRunning ? t("home.btn_cam_stop") : t("home.btn_cam_start");
  });

  const micRunning = !!mic?.running;
  const micAvail = !!mic?.available;
  [el.btnQuickMic, el.btnCalMicToggle].forEach((btn) => {
    if (!btn) return;
    btn.disabled = !micAvail;
    btn.textContent = micRunning ? t("home.btn_mic_stop") : t("home.btn_mic_start");
  });
  if (el.btnMicNoiseCal) {
    el.btnMicNoiseCal.disabled = !micAvail;
  }

  if (camRunning) {
    if (!el.cameraStreamImg.dataset.active) {
      el.cameraStreamImg.src = `/api/camera/stream?t=${Date.now()}`;
      el.cameraStreamImg.dataset.active = "1";
    }
    el.cameraStreamImg.classList.remove("hidden");
    el.cameraPlaceholder.classList.add("hidden");
  } else {
    el.cameraStreamImg.removeAttribute("src");
    delete el.cameraStreamImg.dataset.active;
    el.cameraStreamImg.classList.add("hidden");
    el.cameraPlaceholder.classList.remove("hidden");
    if (!camAvail) {
      el.cameraPlaceholder.textContent = t("cal.cam_placeholder_missing");
    } else if (cam?.status_code === "model_downloading") {
      el.cameraPlaceholder.textContent = t("cal.cam_placeholder_downloading");
    } else {
      el.cameraPlaceholder.textContent = t("cal.cam_placeholder_closed");
    }
  }
}

function renderScanner(scanner) {
  if (!scanner || !scanner.enabled) {
    el.scannerSection.classList.add("hidden");
    return;
  }
  el.scannerSection.classList.remove("hidden");
  el.scannerTiles.innerHTML = "";
  scanner.actions.forEach((action, idx) => {
    const tile = document.createElement("div");
    tile.className = "scan-tile" + (idx === scanner.current_index ? " highlighted" : "");
    tile.setAttribute("role", "listitem");
    const active = scanner.active_toggles?.[action.id];
    const label = t(`scan.${action.id}`);
    tile.textContent = active ? `${label} [${t("scan.toggle_on_suffix")}]` : label;
    el.scannerTiles.appendChild(tile);
  });
}

function renderOutputsLog(outputs) {
  el.outputLog.innerHTML = "";
  if (!outputs || outputs.length === 0) {
    const li = document.createElement("li");
    li.textContent = t("cal.log_empty");
    el.outputLog.appendChild(li);
    return;
  }
  outputs.slice(0, 8).forEach((o) => {
    const li = document.createElement("li");
    const tag = o.adapter === "safe_test_mode" ? `[${t("cal.log_tag_test")}]` : `[${t("cal.log_tag_live")}]`;
    const desc = o.label && state.dict[o.label] ? t(o.label) : (o.label || o.output_type);
    li.textContent = `${tag} ${o.target.toUpperCase()} = ${o.value} — ${desc}`;
    el.outputLog.appendChild(li);
  });
}

function renderVoiceStatus(data) {
  const langs = data.voice_languages || [];
  const langName = LANG_NAMES[state.lang] || state.lang;
  if (langs.includes(state.lang)) {
    el.voiceStatusMsg.textContent = t("set.voice_ok", { language: langName });
  } else {
    el.voiceStatusMsg.textContent = t("voice.missing", { language: langName });
  }
}

function syncChannelThresholds(profile) {
  const rules = profile?.rules || [];
  document.querySelectorAll(".meter-slider").forEach((sl) => {
    const ch = sl.dataset.channel;
    const match = rules.find((r) => {
      if (r.mode === "analog") return false;
      if (ch === "audio_level") {
        return r.channel === "audio_trigger" || r.channel === "audio_loud" || r.channel === "audio_level";
      }
      return r.channel === ch;
    });
    const th = match ? match.threshold : state.channelThresholds[ch] ?? 0.5;
    state.channelThresholds[ch] = th;
    sl.value = th;
    const nameText = t(`cal.meter.${ch}`);
    sl.setAttribute("aria-label", t("cal.slider_aria", { name: nameText }));
    const badge = document.getElementById(`th-${ch}`);
    if (badge) {
      badge.textContent = t("cal.threshold_short", { pct: Math.round(th * 100) });
    }
  });
}

function renderAll(data) {
  state.data = data;
  const s = data.settings;

  document.body.classList.toggle("high-contrast", !!s.high_contrast);
  document.body.classList.toggle("large-text", !!s.large_text);
  el.btnContrast.setAttribute("aria-pressed", String(!!s.high_contrast));
  el.btnLargeText.setAttribute("aria-pressed", String(!!s.large_text));
  el.btnTts.setAttribute("aria-pressed", String(!!s.tts_enabled));
  el.chkSwapEyes.checked = !!s.swap_eyes;
  if (el.chkLowLight) el.chkLowLight.checked = s.low_light_camera_mode !== false;
  if (el.slMicGain && el.lblMicGain) {
    const mg = typeof s.mic_gain === "number" ? s.mic_gain : 4.0;
    el.slMicGain.value = mg;
    el.lblMicGain.textContent = `${mg.toFixed(1)}x`;
  }
  if (el.chkMicNoise) el.chkMicNoise.checked = s.mic_noise_suppression !== false;
  if (el.chkMicAgc) el.chkMicAgc.checked = s.mic_auto_gain !== false;
  populateDeviceSelects();

  const pid = data.active_profile.id;
  el.activeProfileName.textContent = t(`profile.${pid}.name`);
  el.activeProfileDesc.textContent = t(`profile.${pid}.desc`);

  if (s.safe_test_mode) {
    el.btnMode.textContent = t("home.btn_start_live");
    el.btnMode.classList.add("btn-primary");
    el.modeHint.textContent = t("home.hint_safe");
  } else {
    el.btnMode.textContent = t("home.btn_stop_live");
    el.btnMode.classList.remove("btn-primary");
    el.modeHint.textContent = t("home.hint_live");
  }

  const ruleX = data.active_profile.rules.find((r) => r.mode === "analog" && r.target === "mouse_x");
  const ruleY = data.active_profile.rules.find((r) => r.mode === "analog" && r.target === "mouse_y");
  const analogRule = ruleX || data.active_profile.rules.find((r) => r.mode === "analog");

  if (analogRule) {
    el.slSensitivity.value = analogRule.sensitivity;
    el.lblSensitivity.textContent = `${analogRule.sensitivity.toFixed(1)}x`;
    el.slDeadzone.value = analogRule.deadzone;
    const dzPct = Math.round(analogRule.deadzone * 100);
    el.lblDeadzone.textContent = `${dzPct}%`;
    el.reticleDeadzone.style.width = `${dzPct * 2}%`;
    el.reticleDeadzone.style.height = `${dzPct * 2}%`;
    if (el.slSmoothing && el.lblSmoothing) {
      el.slSmoothing.value = analogRule.smoothing;
      el.lblSmoothing.textContent = `${Math.round(analogRule.smoothing * 100)}%`;
    }
  }
  el.chkInvertX.checked = !!ruleX?.invert;
  el.chkInvertY.checked = !!ruleY?.invert;

  syncChannelThresholds(data.active_profile);

  // Active controls cheat-sheet (safe DOM construction)
  el.homeControlsGrid.replaceChildren();
  if (data.active_profile.rules.length === 0) {
    const chip = document.createElement("div");
    chip.className = "control-chip";
    const nameSpan = document.createElement("span");
    nameSpan.textContent = t("home.scanner_title");
    const keySpan = document.createElement("span");
    keySpan.className = "control-key";
    keySpan.textContent = "SPACE";
    chip.append(nameSpan, keySpan);
    el.homeControlsGrid.appendChild(chip);
  } else {
    data.active_profile.rules.forEach((r) => {
      const chip = document.createElement("div");
      chip.className = "control-chip";
      const on = data.active_toggles?.[r.id] ? ` (${t("home.control_on_suffix")})` : "";
      const keySpan = document.createElement("span");
      keySpan.className = "control-key";
      keySpan.textContent = r.target.toUpperCase();
      const nameSpan = document.createElement("span");
      nameSpan.textContent = `${t(`rule.${r.id}`)}${on}`;
      chip.append(nameSpan, keySpan);
      el.homeControlsGrid.appendChild(chip);
    });
  }

  // Profiles Grid (safe DOM construction)
  el.profilesGrid.replaceChildren();
  data.profiles.forEach((p) => {
    const btn = document.createElement("button");
    btn.className = "profile-btn" + (p.id === pid ? " active" : "");
    const titleEl = document.createElement("strong");
    titleEl.textContent = t(`profile.${p.id}.name`);
    const targetEl = document.createElement("span");
    targetEl.className = "profile-target";
    targetEl.textContent = t(`profile.${p.id}.target`);
    const descEl = document.createElement("span");
    descEl.className = "profile-desc";
    descEl.textContent = t(`profile.${p.id}.desc`);
    btn.append(titleEl, targetEl, descEl);
    btn.addEventListener("click", async () => {
      playTone(580, 50);
      renderAll(await apiPost(`/api/profile/${p.id}`));
    });
    el.profilesGrid.appendChild(btn);
  });

  renderVoiceStatus(data);
  updateDeviceButtons(data.inputs);
  renderTelemetry(data.telemetry, data.inputs);
  renderScanner(data.scanner);
  renderOutputsLog(data.recent_outputs);
}

function populateDeviceSelects() {
  const s = state.data?.settings;
  if (el.selCamera) {
    const curCam = s?.camera_index ?? 0;
    const cams = state.devices.cameras.length
      ? [...state.devices.cameras]
      : [{ index: curCam, label: t("cal.cam_default_option", { index: curCam }) }];
    if (!cams.some((c) => c.index === curCam)) {
      cams.unshift({ index: curCam, label: t("cal.cam_default_option", { index: curCam }) });
    }
    el.selCamera.replaceChildren();
    cams.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = String(c.index);
      opt.textContent = state.devices.cameras.length ? c.label : t("cal.cam_default_option", { index: c.index });
      el.selCamera.appendChild(opt);
    });
    el.selCamera.value = String(curCam);
  }

  if (el.selMic) {
    const curMic = s?.mic_device_index;
    el.selMic.replaceChildren();
    const defOpt = document.createElement("option");
    defOpt.value = "";
    defOpt.textContent = t("cal.mic_default_option");
    el.selMic.appendChild(defOpt);
    state.devices.microphones.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = String(m.index);
      opt.textContent = m.name;
      el.selMic.appendChild(opt);
    });
    el.selMic.value = curMic === null || curMic === undefined ? "" : String(curMic);
  }
}

async function refreshDevices() {
  if (el.btnRefreshDevices) el.btnRefreshDevices.disabled = true;
  try {
    const res = await apiGet("/api/devices");
    state.devices = {
      cameras: Array.isArray(res?.cameras) ? res.cameras : [],
      microphones: Array.isArray(res?.microphones) ? res.microphones : [],
    };
    state.devicesLoaded = true;
    populateDeviceSelects();
  } finally {
    if (el.btnRefreshDevices) el.btnRefreshDevices.disabled = false;
  }
}

function renderTelemetry(telemetry, inputs = []) {
  const camInput = inputs.find((i) => i.name === "face_tracker");
  const camTel = telemetry?.camera;
  if (el.camTelemetry) {
    if (camInput?.running && camTel) {
      const lightKey = `cal.light.${camTel.light_status || "unknown"}`;
      const faceText = camTel.face_detected ? t("cal.face_locked") : t("cal.face_missing");
      let line = t("cal.cam_status_line", {
        fps: Math.round(camTel.fps || 0),
        light: t(lightKey),
        face: faceText,
      });
      if (camTel.enhanced) {
        line += ` · ${t("cal.boost_active")}`;
      }
      el.camTelemetry.textContent = line;
      el.camTelemetry.classList.remove("hidden");
    } else {
      el.camTelemetry.classList.add("hidden");
    }
  }

  const micTel = telemetry?.microphone;
  if (el.micTelemetry && micTel) {
    if (micTel.calibrating_noise) {
      el.micTelemetry.textContent = t("cal.mic_calibrating");
    } else {
      el.micTelemetry.textContent = t("cal.mic_status_line", {
        sr: micTel.samplerate || 16000,
        floor: Math.round((micTel.noise_floor || 0) * 100),
        gain: (micTel.effective_gain || 4).toFixed(1),
      });
    }
  }
}

/* System Diagnostics */
async function runDiagnostics() {
  el.btnRunDiag.disabled = true;
  const loadingRow = document.createElement("div");
  loadingRow.className = "diag-item";
  const loadingSpan = document.createElement("span");
  loadingSpan.textContent = t("set.diag_running");
  loadingRow.appendChild(loadingSpan);
  el.diagList.replaceChildren(loadingRow);
  try {
    const res = await apiGet("/api/diagnostics");
    const icons = { ok: "✓", warn: "⚠", fail: "✗" };
    el.diagList.replaceChildren();
    (res.checks || []).forEach((c) => {
      const row = document.createElement("div");
      row.className = "diag-item";
      const left = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = `${icons[c.status] || "•"} ${t(`diag.${c.id}`)}`;
      left.appendChild(title);
      if (c.detail) {
        const det = document.createElement("div");
        det.className = "diag-detail";
        det.textContent = c.detail;
        left.appendChild(det);
      }
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = t(`diag.status.${c.status}`);
      row.appendChild(left);
      row.appendChild(badge);
      el.diagList.appendChild(row);
    });
  } finally {
    el.btnRunDiag.disabled = false;
  }
}

/* Setup Wizard */
function openWizard() {
  state.wizardStep = 0;
  state.wizardResult = null;
  el.wizardBackdrop.classList.remove("hidden");
  renderWizardStep(false);
}

async function closeWizard(persistDone = true) {
  el.wizardBackdrop.classList.add("hidden");
  if (persistDone && state.data?.settings && !state.data.settings.onboarding_done) {
    renderAll(await apiPost("/api/settings", { ...state.data.settings, onboarding_done: true }));
  }
}

function renderWizardStep(shouldSpeak = true) {
  const steps = getWizardSteps();
  if (state.wizardStep < steps.length) {
    const step = steps[state.wizardStep];
    el.wizardStepTag.textContent = t("wizard.step_tag", {
      current: state.wizardStep + 1,
      total: steps.length,
    });
    el.wizardTitle.textContent = t("wizard.title");
    el.wizardQuestion.textContent = step.question;
    el.btnWizardPrev.disabled = state.wizardStep === 0;
    el.btnWizardNext.textContent = state.wizardStep === steps.length - 1 ? t("wizard.recommend") : t("wizard.next");

    const grid = document.createElement("div");
    grid.className = "wizard-choices";
    step.options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.className = "choice-btn";
      const selected =
        step.key === "__lang__"
          ? state.lang === opt.id
          : step.multi
          ? state.wizardAnswers[step.key].includes(opt.id)
          : state.wizardAnswers[step.key] === opt.id;
      btn.setAttribute("aria-pressed", String(selected));
      const titleEl = document.createElement("strong");
      titleEl.textContent = opt.title;
      const descEl = document.createElement("small");
      descEl.textContent = opt.desc;
      btn.append(titleEl, descEl);
      btn.addEventListener("click", async () => {
        playTone(560, 45);
        if (step.key === "__lang__") {
          await setLanguage(opt.id);
          renderWizardStep(false);
          return;
        }
        if (step.multi) {
          const arr = state.wizardAnswers[step.key];
          const idx = arr.indexOf(opt.id);
          if (idx >= 0) arr.splice(idx, 1);
          else arr.push(opt.id);
        } else {
          state.wizardAnswers[step.key] = opt.id;
        }
        renderWizardStep(false);
      });
      grid.appendChild(btn);
    });
    el.wizardBody.innerHTML = "";
    el.wizardBody.appendChild(grid);
    if (shouldSpeak && step.key !== "__lang__") announce(step.question, true);
    return;
  }

  const rec = state.wizardResult;
  const summaryText = t(rec.summary_key);
  const hintsList = t(rec.hints_key);
  el.wizardStepTag.textContent = t("wizard.done_tag");
  el.wizardTitle.textContent = t("wizard.done_title");
  el.wizardQuestion.textContent = summaryText;
  el.btnWizardPrev.disabled = false;
  el.btnWizardNext.textContent = t("wizard.apply");

  const ul = document.createElement("ul");
  ul.className = "clean-list";
  (Array.isArray(hintsList) ? hintsList : [String(hintsList)]).forEach((h) => {
    const li = document.createElement("li");
    li.textContent = h;
    ul.appendChild(li);
  });
  el.wizardBody.innerHTML = "";
  el.wizardBody.appendChild(ul);
  if (shouldSpeak) announce(summaryText, true);
}

async function triggerPulse(channel, source) {
  playTone(680, 45);
  updateSignalVisuals(channel, 0.9);
  await apiPost("/api/simulate", { channel, value: 1.0, source });
  setTimeout(() => {
    updateSignalVisuals(channel, 0.0);
    apiPost("/api/simulate", { channel, value: 0.0, source });
  }, 160);
}

function bindEvents() {
  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.addEventListener("click", () => switchTab(b.dataset.tab));
  });

  el.btnGotoCalibrate.addEventListener("click", () => switchTab("calibrate"));
  el.btnOpenWizard.addEventListener("click", openWizard);
  el.btnWizardClose.addEventListener("click", () => closeWizard(true));

  el.btnWizardPrev.addEventListener("click", () => {
    if (state.wizardStep > 0) {
      state.wizardStep -= 1;
      renderWizardStep(true);
    }
  });

  el.btnWizardNext.addEventListener("click", async () => {
    const total = getWizardSteps().length;
    if (state.wizardStep < total - 1) {
      state.wizardStep += 1;
      renderWizardStep(true);
    } else if (state.wizardStep === total - 1) {
      state.wizardResult = await apiPost("/api/wizard/recommend", state.wizardAnswers);
      state.wizardStep = total;
      renderWizardStep(true);
    } else {
      renderAll(await apiPost("/api/wizard/apply", state.wizardAnswers));
      await closeWizard(false);
    }
  });

  [el.langSelect, el.setLangSelect].forEach((sel) => {
    if (sel) sel.addEventListener("change", (e) => setLanguage(e.target.value));
  });

  el.btnMode.addEventListener("click", async () => {
    const next = { ...state.data.settings, safe_test_mode: !state.data.settings.safe_test_mode };
    renderAll(await apiPost("/api/settings", next));
  });

  [el.btnQuickCam, el.btnCalCamToggle].forEach((btn) => {
    btn.addEventListener("click", async () => {
      renderAll(await apiPost("/api/inputs/face_tracker/toggle"));
    });
  });

  [el.btnQuickMic, el.btnCalMicToggle].forEach((btn) => {
    if (!btn) return;
    btn.addEventListener("click", async () => {
      renderAll(await apiPost("/api/inputs/audio_trigger/toggle"));
    });
  });

  if (el.btnRefreshDevices) {
    el.btnRefreshDevices.addEventListener("click", () => {
      refreshDevices().catch(() => {});
    });
  }
  if (el.selCamera) {
    el.selCamera.addEventListener("change", async (e) => {
      const idx = parseInt(e.target.value, 10) || 0;
      renderAll(await apiPost("/api/settings", { ...state.data.settings, camera_index: idx }));
    });
  }
  if (el.chkLowLight) {
    el.chkLowLight.addEventListener("change", async (e) => {
      renderAll(await apiPost("/api/settings", { ...state.data.settings, low_light_camera_mode: e.target.checked }));
    });
  }
  if (el.selMic) {
    el.selMic.addEventListener("change", async (e) => {
      const val = e.target.value === "" ? null : parseInt(e.target.value, 10);
      renderAll(await apiPost("/api/settings", { ...state.data.settings, mic_device_index: val }));
    });
  }
  if (el.btnMicNoiseCal) {
    el.btnMicNoiseCal.addEventListener("click", async () => {
      playTone(520, 60);
      renderAll(await apiPost("/api/audio/calibrate-noise"));
    });
  }
  if (el.slMicGain) {
    el.slMicGain.addEventListener("input", (e) => {
      if (el.lblMicGain) {
        el.lblMicGain.textContent = `${parseFloat(e.target.value).toFixed(1)}x`;
      }
    });
    el.slMicGain.addEventListener("change", async (e) => {
      const mg = parseFloat(e.target.value);
      renderAll(await apiPost("/api/settings", { ...state.data.settings, mic_gain: mg }));
    });
  }
  if (el.chkMicNoise) {
    el.chkMicNoise.addEventListener("change", async (e) => {
      renderAll(await apiPost("/api/settings", { ...state.data.settings, mic_noise_suppression: e.target.checked }));
    });
  }
  if (el.chkMicAgc) {
    el.chkMicAgc.addEventListener("change", async (e) => {
      renderAll(await apiPost("/api/settings", { ...state.data.settings, mic_auto_gain: e.target.checked }));
    });
  }

  el.btnCalibrate.addEventListener("click", async () => {
    playTone(540, 80);
    renderAll(await apiPost("/api/calibrate", { channels: ["head_yaw", "head_pitch", "gaze_x", "gaze_y"], reset: false }));
  });

  el.btnCalibrateReset.addEventListener("click", async () => {
    renderAll(await apiPost("/api/calibrate", { reset: true }));
  });

  el.slSensitivity.addEventListener("change", async (e) => {
    renderAll(await apiPost("/api/tuning", { sensitivity: parseFloat(e.target.value) }));
  });
  el.slDeadzone.addEventListener("change", async (e) => {
    renderAll(await apiPost("/api/tuning", { deadzone: parseFloat(e.target.value) }));
  });
  if (el.slSmoothing) {
    el.slSmoothing.addEventListener("input", (e) => {
      if (el.lblSmoothing) {
        el.lblSmoothing.textContent = `${Math.round(parseFloat(e.target.value) * 100)}%`;
      }
    });
    el.slSmoothing.addEventListener("change", async (e) => {
      renderAll(await apiPost("/api/tuning", { smoothing: parseFloat(e.target.value) }));
    });
  }

  document.querySelectorAll(".meter-slider").forEach((sl) => {
    const ch = sl.dataset.channel;
    sl.addEventListener("input", (e) => {
      const val = parseFloat(e.target.value);
      state.channelThresholds[ch] = val;
      const badge = document.getElementById(`th-${ch}`);
      if (badge) {
        badge.textContent = t("cal.threshold_short", { pct: Math.round(val * 100) });
      }
    });
    sl.addEventListener("change", async (e) => {
      const val = parseFloat(e.target.value);
      state.channelThresholds[ch] = val;
      renderAll(await apiPost("/api/tuning", { channel_thresholds: { [ch]: val } }));
    });
  });

  el.chkSwapEyes.addEventListener("change", async (e) => {
    renderAll(await apiPost("/api/settings", { ...state.data.settings, swap_eyes: e.target.checked }));
  });
  el.chkInvertX.addEventListener("change", async (e) => {
    renderAll(await apiPost("/api/tuning", { invert_x: e.target.checked }));
  });
  el.chkInvertY.addEventListener("change", async (e) => {
    renderAll(await apiPost("/api/tuning", { invert_y: e.target.checked }));
  });

  el.btnContrast.addEventListener("click", async () => {
    renderAll(await apiPost("/api/settings", { ...state.data.settings, high_contrast: !state.data.settings.high_contrast }));
  });
  el.btnLargeText.addEventListener("click", async () => {
    renderAll(await apiPost("/api/settings", { ...state.data.settings, large_text: !state.data.settings.large_text }));
  });
  el.btnTts.addEventListener("click", async () => {
    renderAll(await apiPost("/api/settings", { ...state.data.settings, tts_enabled: !state.data.settings.tts_enabled }));
  });

  el.btnRunDiag.addEventListener("click", runDiagnostics);

  el.btnEmergency.addEventListener("click", async () => {
    playTone(280, 180);
    renderAll(await apiPost("/api/emergency-stop"));
  });

  el.btnBigSwitch.addEventListener("click", () => triggerPulse("switch_1", "keyboard_assist"));

  document.querySelectorAll(".sim-btn").forEach((btn) => {
    btn.addEventListener("click", () => triggerPulse(btn.dataset.channel, btn.dataset.source));
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "F12") {
      e.preventDefault();
      el.btnEmergency.click();
    } else if (e.code === "Space" && state.data?.scanner?.enabled && el.wizardBackdrop.classList.contains("hidden")) {
      if (document.activeElement?.tagName !== "BUTTON") {
        e.preventDefault();
        triggerPulse("switch_1", "keyboard_assist");
      }
    }
  });
}

function connectWS() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws`);
  state.ws = ws;
  ws.onopen = () => {
    state.wsConnected = true;
    el.wsStatus.textContent = t("home.status_ready");
  };
  ws.onclose = () => {
    state.wsConnected = false;
    el.wsStatus.textContent = t("home.status_connecting");
    setTimeout(connectWS, 1500);
  };
  ws.onmessage = async (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === "state") {
      const incomingLang = msg.state?.settings?.language || "en";
      if (incomingLang !== state.lang || Object.keys(state.dict).length === 0) {
        await fetchLocale(incomingLang);
        applyTranslations();
      }
      renderAll(msg.state);
      if (!msg.state.settings.onboarding_done && !state.wizardShown) {
        state.wizardShown = true;
        openWizard();
      }
    } else if (msg.type === "signals") {
      Object.entries(msg.values || {}).forEach(([ch, val]) => updateSignalVisuals(ch, val));
    } else if (msg.type === "telemetry" && state.data) {
      state.data.telemetry = msg.telemetry;
      renderTelemetry(msg.telemetry, state.data.inputs || []);
    } else if (msg.type === "announcement") {
      announce(msg.text, false);
    } else if (msg.type === "scanner") {
      playTone(440, 35);
      if (state.data) {
        state.data.scanner = msg.scanner;
        renderScanner(msg.scanner);
      }
    } else if (msg.type === "output" && state.data) {
      state.data.recent_outputs.unshift(msg.output);
      state.data.recent_outputs = state.data.recent_outputs.slice(0, 15);
      state.data.active_toggles = msg.active_toggles;
      state.data.scanner = msg.scanner;
      renderOutputsLog(state.data.recent_outputs);
      renderScanner(state.data.scanner);
    }
  };
}

async function init() {
  bindEvents();
  try {
    const initial = await apiGet("/api/state");
    await fetchLocale(initial.settings?.language || "en");
    applyTranslations();
    renderAll(initial);
    if (!initial.settings?.onboarding_done && !state.wizardShown) {
      state.wizardShown = true;
      openWizard();
    }
  } catch (_) {}
  connectWS();
}

init();
