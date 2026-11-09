// DCLED STUDIO // Frontend Controller & Realtime Matrix Renderer
const LEDSX = 21;
const LEDSY = 7;

let liveGridNodes = [];
let testGridNodes = [];
let codeMirrorEditor = null;
let ws = null;
let currentState = null;
let currentTab = "live";
let activeErrorLineHandle = null;

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  initGrid("live-matrix-grid", liveGridNodes);
  initGrid("test-matrix-grid", testGridNodes);
  initCodeMirror();
  initClock();
  initSavedTab();
  fetchInitialState();
  initWebSocket();
});

// Tab Switching
function switchTab(tabId) {
  currentTab = tabId;
  localStorage.setItem("dcled_active_tab", tabId);

  const liveBtn = document.getElementById("tab-btn-live");
  const devBtn = document.getElementById("tab-btn-dev");
  const livePane = document.getElementById("tab-content-live");
  const devPane = document.getElementById("tab-content-dev");

  if (tabId === "live") {
    liveBtn.classList.add("active");
    liveBtn.setAttribute("aria-selected", "true");
    devBtn.classList.remove("active");
    devBtn.setAttribute("aria-selected", "false");

    livePane.classList.add("active");
    devPane.classList.remove("active");
  } else {
    devBtn.classList.add("active");
    devBtn.setAttribute("aria-selected", "true");
    liveBtn.classList.remove("active");
    liveBtn.setAttribute("aria-selected", "false");

    devPane.classList.add("active");
    livePane.classList.remove("active");

    // Refresh CodeMirror so lines calculate correctly when becoming visible
    setTimeout(() => {
      if (codeMirrorEditor) {
        codeMirrorEditor.refresh();
      }
    }, 50);
  }
}

function initSavedTab() {
  const urlParams = new URLSearchParams(window.location.search);
  const tabParam = urlParams.get("tab");
  if (tabParam === "dev" || tabParam === "live") {
    switchTab(tabParam);
    return;
  }
  const savedTab = localStorage.getItem("dcled_active_tab");
  if (savedTab === "dev" || savedTab === "live") {
    switchTab(savedTab);
  }
}

// Create 21x7 circular LED nodes
function initGrid(containerId, nodeArray) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  nodeArray.length = 0;

  for (let y = 0; y < LEDSY; y++) {
    for (let x = 0; x < LEDSX; x++) {
      const node = document.createElement("div");
      node.className = "led";
      node.dataset.x = x;
      node.dataset.y = y;
      container.appendChild(node);
      nodeArray.push(node);
    }
  }
}

// Update LED nodes given a 21x7 matrix buffer: buffer[x][y]
function renderMatrixToGrid(buffer, nodeArray) {
  if (!buffer || buffer.length !== LEDSX) return;

  for (let y = 0; y < LEDSY; y++) {
    for (let x = 0; x < LEDSX; x++) {
      const index = y * LEDSX + x;
      const isLit = buffer[x] && buffer[x][y] === 1;
      const node = nodeArray[index];
      if (node) {
        if (isLit) {
          node.classList.add("lit");
        } else {
          node.classList.remove("lit");
        }
      }
    }
  }
}

// Initialize CodeMirror IDE for Python script editing
function initCodeMirror() {
  const textarea = document.getElementById("script-editor");
  if (!textarea) return;
  codeMirrorEditor = CodeMirror.fromTextArea(textarea, {
    mode: "python",
    theme: "nord",
    lineNumbers: true,
    tabSize: 4,
    indentUnit: 4,
    indentWithTabs: false
  });
}

// Retro digital clock
function initClock() {
  const clockEl = document.getElementById("system-clock");
  function update() {
    const d = new Date();
    clockEl.innerText = d.toTimeString().substring(0, 8);
  }
  setInterval(update, 1000);
  update();
}

// Fetch complete initial state from backend
async function fetchInitialState() {
  try {
    const res = await fetch("/api/state");
    const data = await res.json();
    currentState = data;
    applyStateToUI(data);
    if (codeMirrorEditor) {
      // Prioritize dev_settings.script_code if user previously worked on a script in Development
      const devCode = (data.dev_settings && data.dev_settings.script_code) ? data.dev_settings.script_code : data.script_code;
      if (devCode) {
        codeMirrorEditor.setValue(devCode);
      }
    }
  } catch (err) {
    appendLiveLog(`Failed to connect to backend: ${err.message}`, "error");
  }
}

// Connect to high-frequency WebSocket telemetry
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    appendLiveLog("[WEBSOCKET] Realtime matrix stream connected.", "system");
  };

  ws.onmessage = (event) => {
    try {
      const state = JSON.parse(event.data);
      currentState = state;
      applyStateToUI(state);
    } catch (e) {
      console.error("WS Parse error", e);
    }
  };

  ws.onclose = () => {
    appendLiveLog("[WEBSOCKET] Stream disconnected. Reconnecting in 2s...", "error");
    setTimeout(initWebSocket, 2000);
  };
}

// Apply telemetry update to UI elements
function applyStateToUI(state) {
  // Update Live Matrix Display
  if (state.live_matrix) {
    renderMatrixToGrid(state.live_matrix, liveGridNodes);
  }
  // Update Test Matrix Display ONLY when not actively animating in preview
  if (state.test_matrix && !isTestAnimating) {
    renderMatrixToGrid(state.test_matrix, testGridNodes);
  }

  // Update Live Text Marquee
  document.getElementById("live-text-preview").innerText = state.current_text || "---";
  if (state.test_text) {
    document.getElementById("test-text-preview").innerText = state.test_text;
  }
  document.getElementById("live-effect-label").innerText = `EFFECT: ${state.effect.toUpperCase()}`;

  // Update USB Badge
  const usbBadge = document.getElementById("usb-badge");
  const usbText = document.getElementById("usb-text");
  if (state.usb && state.usb.connected) {
    usbBadge.className = "telemetry-pill pill-connected";
    usbText.innerText = "CONNECTED (VID:1d34)";
  } else {
    usbBadge.className = "telemetry-pill pill-disconnected";
    usbText.innerText = "VIRTUAL SIMULATOR";
  }

  // Update Service Badge
  const serviceBadge = document.getElementById("service-badge");
  const serviceText = document.getElementById("service-text");
  if (state.service_running) {
    serviceBadge.className = "telemetry-pill pill-running";
    serviceText.innerText = "STARTED";
    document.getElementById("btn-start").disabled = true;
    document.getElementById("btn-stop").disabled = false;
  } else {
    serviceBadge.className = "telemetry-pill pill-disconnected";
    serviceText.innerText = "STOPPED";
    document.getElementById("btn-start").disabled = false;
    document.getElementById("btn-stop").disabled = true;
  }

  // Sync LIVE Controls
  syncIfUnfocused("select-effect", state.effect);
  syncIfUnfocused("input-interval", state.interval_seconds);
  syncIfUnfocused("input-speed", state.speed_ms);
  syncIfUnfocused("select-brightness", state.brightness);
  if (state.font) syncIfUnfocused("select-font", state.font);
  if (state.spacing) syncIfUnfocused("select-spacing", state.spacing);
  document.getElementById("speed-val").innerText = state.speed_ms + "ms";

  // Sync DEV Controls (from dev_settings object if available)
  const dev = state.dev_settings || {};
  syncIfUnfocused("dev-select-effect", dev.effect || state.effect);
  syncIfUnfocused("dev-input-interval", dev.interval_seconds || state.interval_seconds);
  syncIfUnfocused("dev-input-speed", dev.speed_ms || state.speed_ms);
  syncIfUnfocused("dev-select-brightness", dev.brightness !== undefined ? dev.brightness : state.brightness);
  syncIfUnfocused("dev-select-font", dev.font || state.font || "default");
  syncIfUnfocused("dev-select-spacing", dev.spacing || state.spacing || "proportional");
  document.getElementById("dev-speed-val").innerText = (dev.speed_ms || state.speed_ms) + "ms";

  // Sync Live Logs
  if (state.logs && state.logs.length) {
    const term = document.getElementById("terminal-live");
    term.innerHTML = "";
    state.logs.forEach(log => {
      const line = document.createElement("div");
      line.className = "log-entry";
      if (log.includes("ERROR") || log.includes("failed")) line.classList.add("error");
      else if (log.includes("USB")) line.classList.add("usb");
      else if (log.includes("Service")) line.classList.add("system");
      line.innerText = log;
      term.appendChild(line);
    });
    term.scrollTop = term.scrollHeight;
  }
}

function syncIfUnfocused(id, val) {
  const el = document.getElementById(id);
  if (el && document.activeElement !== el) {
    el.value = val;
  }
}

// Start / Stop service
async function setServiceState(running) {
  try {
    const res = await fetch("/api/service/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ running })
    });
    const data = await res.json();
    appendLiveLog(`Service manually set to: ${running ? 'RUNNING' : 'STOPPED'}`, "system");
  } catch (e) {
    appendLiveLog(`Service state toggle error: ${e.message}`, "error");
  }
}

// Reconnect USB
async function reconnectUSB() {
  try {
    appendLiveLog("Scanning USB bus for Dream Cheeky (0x1d34:0x0013)...", "usb");
    const res = await fetch("/api/service/reconnect", { method: "POST" });
    const data = await res.json();
    if (data.reconnected) {
      appendLiveLog("Device successfully discovered and reconnected!", "usb");
    } else {
      appendLiveLog("Hardware not detected. Operating seamlessly in simulation mode.", "system");
    }
  } catch (e) {
    appendLiveLog(`Scan USB error: ${e.message}`, "error");
  }
}

// Update LIVE settings
async function updateSettings() {
  const effect = document.getElementById("select-effect").value;
  const interval_seconds = parseInt(document.getElementById("input-interval").value, 10) || 30;
  const speed_ms = parseInt(document.getElementById("input-speed").value, 10) || 40;
  const brightness = parseInt(document.getElementById("select-brightness").value, 10) || 2;
  const font = document.getElementById("select-font") ? document.getElementById("select-font").value : "default";
  const spacing = document.getElementById("select-spacing") ? document.getElementById("select-spacing").value : "proportional";

  try {
    await fetch("/api/config/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ effect, interval_seconds, speed_ms, brightness, font, spacing })
    });
    appendLiveLog(`Live settings updated (Font: ${font}, Spacing: ${spacing}, Effect: ${effect})`, "system");
  } catch (e) {
    console.error("Update live settings failed", e);
  }
}

// Update DEV settings (persisted in config.json under dev_settings)
async function updateDevSettings() {
  const effect = document.getElementById("dev-select-effect").value;
  const interval_seconds = parseInt(document.getElementById("dev-input-interval").value, 10) || 30;
  const speed_ms = parseInt(document.getElementById("dev-input-speed").value, 10) || 40;
  const brightness = parseInt(document.getElementById("dev-select-brightness").value, 10) || 2;
  const font = document.getElementById("dev-select-font").value;
  const spacing = document.getElementById("dev-select-spacing").value;

  try {
    await fetch("/api/config/dev_settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ effect, interval_seconds, speed_ms, brightness, font, spacing })
    });
    appendDevLog(`Dev sandbox settings updated (Font: ${font}, Spacing: ${spacing}, Effect: ${effect})`, "system");
    refreshTestAnimationIfActive();
  } catch (e) {
    console.error("Update dev settings failed", e);
  }
}

// Error highlighting in CodeMirror
function clearEditorHighlights() {
  if (activeErrorLineHandle && codeMirrorEditor) {
    codeMirrorEditor.removeLineClass(activeErrorLineHandle, "background", "cm-error-line");
    activeErrorLineHandle = null;
  }
}

function highlightErrorLine(lineNumber) {
  clearEditorHighlights();
  if (codeMirrorEditor && lineNumber && lineNumber > 0) {
    const lineIdx = lineNumber - 1;
    activeErrorLineHandle = codeMirrorEditor.addLineClass(lineIdx, "background", "cm-error-line");
    codeMirrorEditor.setCursor({ line: lineIdx, ch: 0 });
  }
}

// Format Python Code
async function formatCode(style = "spaces") {
  if (!codeMirrorEditor) return;
  const code = codeMirrorEditor.getValue();
  appendDevLog(`Formatting script (${style === 'spaces' ? '4 Spaces' : 'Tabs'})...`, "system");

  try {
    const res = await fetch("/api/script/format", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, indent_style: style, indent_size: 4 })
    });
    const data = await res.json();
    if (data.success) {
      codeMirrorEditor.setValue(data.formatted_code);
      clearEditorHighlights();
      appendDevLog("✨ Code formatted successfully! Clean 4-space indentation applied.", "system");
    } else {
      appendDevLog(`Format error: ${data.message}`, "error");
    }
  } catch (e) {
    appendDevLog(`Format request failed: ${e.message}`, "error");
  }
}

// Convert all tabs to 4 spaces
async function convertTabsToSpaces() {
  formatCode("spaces");
}

// Validate Python Syntax & Indentation
async function validateSyntax() {
  if (!codeMirrorEditor) return;
  const code = codeMirrorEditor.getValue();
  appendDevLog("Validating Python syntax & indentation...", "system");

  try {
    const res = await fetch("/api/script/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code })
    });
    const result = await res.json();

    if (result.valid) {
      clearEditorHighlights();
      appendDevLog("✓ Python syntax and indentation are valid!", "system");
    } else {
      highlightErrorLine(result.line);
      let errMsg = `❌ Syntax Check Failed: [Line ${result.line || '?'}] ${result.error_type}: ${result.message}`;
      if (result.hint) {
        errMsg += `\n💡 Hint: ${result.hint}`;
      }
      appendDevLog(errMsg, "error");
    }
  } catch (e) {
    appendDevLog(`Syntax validation failed: ${e.message}`, "error");
  }
}

// Save script to local disk (.py file)
function saveScriptToDisk() {
  if (!codeMirrorEditor) return;
  const code = codeMirrorEditor.getValue();
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const filename = `dcled_script_${timestamp}.py`;

  const blob = new Blob([code], { type: "text/x-python;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  appendDevLog(`💾 Script saved to local disk as '${filename}'`, "system");
}

// Trigger browser file picker to load script from local disk
function triggerLoadFromDisk() {
  const fileInput = document.getElementById("file-input-disk");
  if (fileInput) {
    fileInput.value = "";
    fileInput.click();
  }
}

// Handle file chosen from disk
function handleFileLoaded(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function(e) {
    const contents = e.target.result;
    if (codeMirrorEditor) {
      codeMirrorEditor.setValue(contents);
      clearEditorHighlights();
      appendDevLog(`📂 Loaded script from disk: '${file.name}' (${contents.length} bytes)`, "system");
    }
  };
  reader.onerror = function() {
    appendDevLog(`Failed to read file: ${file.name}`, "error");
  };
  reader.readAsText(file);
}

let isTestAnimating = false;
let testAnimationTimer = null;
let testAnimationFrames = [];
let currentTestFrameIndex = 0;
let lastStaticTestMatrix = null;

// Get current dev speed in milliseconds with sensible bounds
function getDevSpeedMs() {
  const speedInput = document.getElementById("dev-input-speed");
  let val = speedInput ? parseInt(speedInput.value, 10) : 40;
  if (isNaN(val) || val < 10) val = 10;
  if (val > 1000) val = 1000;
  return val;
}

// Stop animation if running
function stopTestAnimation() {
  if (testAnimationTimer) {
    clearTimeout(testAnimationTimer);
    testAnimationTimer = null;
  }
  isTestAnimating = false;
  const btn = document.getElementById("btn-enable-effect");
  if (btn) {
    btn.innerHTML = `<span id="anim-icon">▶</span> ENABLE EFFECT`;
    btn.classList.remove("btn-active");
  }
  // Restore static frame if available
  if (lastStaticTestMatrix) {
    renderMatrixToGrid(lastStaticTestMatrix, testGridNodes);
  }
}

// Tick function with dynamic speed reading and loop-end pause
function stepTestAnimation() {
  if (!isTestAnimating || !testAnimationFrames.length) {
    stopTestAnimation();
    return;
  }

  // Render current frame
  renderMatrixToGrid(testAnimationFrames[currentTestFrameIndex], testGridNodes);

  // Determine delay to next frame
  const currentSpeed = getDevSpeedMs();
  const effect = document.getElementById("dev-select-effect") ? document.getElementById("dev-select-effect").value : "static";

  let nextDelay = currentSpeed;
  if (effect === "flash") {
    // Flashing effect should have readable blink cadence scaled to speed
    nextDelay = Math.max(120, currentSpeed * 4);
  } else if (effect === "scroll_north" || effect === "scroll_south") {
    // Vertical scrolls have only 15 frames for 7 rows; scale up to maintain smooth readable pacing
    nextDelay = Math.max(80, currentSpeed * 2.8);
  }

  const isLastFrame = (currentTestFrameIndex === testAnimationFrames.length - 1);
  if (isLastFrame && testAnimationFrames.length > 1) {
    // Natural loop boundary pause before replaying
    if (effect === "flash") {
      nextDelay = Math.max(250, currentSpeed * 6);
    } else if (effect === "scroll_north" || effect === "scroll_south") {
      nextDelay = Math.max(400, currentSpeed * 5);
    } else {
      nextDelay = Math.max(350, currentSpeed * 8);
    }
  }

  currentTestFrameIndex = (currentTestFrameIndex + 1) % testAnimationFrames.length;

  testAnimationTimer = setTimeout(stepTestAnimation, nextDelay);
}

// Toggle Enable / Disable test effect
async function toggleTestAnimation() {
  if (isTestAnimating) {
    stopTestAnimation();
    appendDevLog("Effect preview disabled.", "system");
    return;
  }

  const text = document.getElementById("test-text-preview").innerText;
  if (!text || text === "Ready to test script" || text === "INITIALIZING...") {
    appendDevLog("Please run 'TEST SCRIPT' first to generate text for preview.", "error");
    return;
  }

  const effect = document.getElementById("dev-select-effect").value;
  const font = document.getElementById("dev-select-font").value;
  const spacing = document.getElementById("dev-select-spacing").value;
  const speed = getDevSpeedMs();

  appendDevLog(`Fetching animation frames for '${effect}'...`, "system");

  try {
    const res = await fetch("/api/script/preview_frames", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, effect, font, spacing })
    });
    const data = await res.json();
    testAnimationFrames = data.frames || [];

    if (!testAnimationFrames.length) {
      appendDevLog("No frames generated for this effect.", "error");
      return;
    }

    isTestAnimating = true;
    currentTestFrameIndex = 0;
    const btn = document.getElementById("btn-enable-effect");
    if (btn) {
      btn.innerHTML = `<span id="anim-icon">⏹</span> DISABLE EFFECT`;
      btn.classList.add("btn-active");
    }

    appendDevLog(`▶ Effect '${effect}' enabled (${testAnimationFrames.length} frames, base speed: ${speed}ms)`, "system");
    stepTestAnimation();
  } catch (e) {
    appendDevLog(`Failed to start effect preview: ${e.message}`, "error");
    stopTestAnimation();
  }
}

// Auto-refresh preview frames if effect or typography is changed while effect is enabled
async function refreshTestAnimationIfActive() {
  if (!isTestAnimating) return;
  const text = document.getElementById("test-text-preview").innerText;
  if (!text || text === "Ready to test script" || text === "INITIALIZING...") return;

  const effect = document.getElementById("dev-select-effect").value;
  const font = document.getElementById("dev-select-font").value;
  const spacing = document.getElementById("dev-select-spacing").value;

  try {
    const res = await fetch("/api/script/preview_frames", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, effect, font, spacing })
    });
    const data = await res.json();
    if (data.frames && data.frames.length) {
      testAnimationFrames = data.frames;
      currentTestFrameIndex = 0;
    }
  } catch (e) {
    console.error("Failed to refresh test animation frames", e);
  }
}

// Test script in sandbox without affecting live display
async function runScriptTest() {
  if (!codeMirrorEditor) return;
  stopTestAnimation();
  clearEditorHighlights();
  const code = codeMirrorEditor.getValue();
  // Use DEV tuning controls for test rendering
  const font = document.getElementById("dev-select-font").value;
  const spacing = document.getElementById("dev-select-spacing").value;
  appendDevLog("Executing script test in sandbox...", "system");

  try {
    const res = await fetch("/api/script/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, font, spacing })
    });
    const result = await res.json();

    document.getElementById("test-duration-label").innerText = `EXEC: ${result.duration_ms.toFixed(1)}ms`;
    document.getElementById("test-text-preview").innerText = result.result_text;

    if (result.matrix) {
      lastStaticTestMatrix = result.matrix;
      renderMatrixToGrid(result.matrix, testGridNodes);
    }

    if (result.success) {
      appendDevLog(`Test succeeded in ${result.duration_ms.toFixed(1)}ms -> Output: "${result.result_text}"`, "system");
      if (result.stdout && result.stdout.trim()) {
        appendDevLog(`[STDOUT]\n${result.stdout.trim()}`, "normal");
      }
    } else {
      if (result.error_details && result.error_details.line) {
        highlightErrorLine(result.error_details.line);
      }
      appendDevLog(`Test script error: ${result.result_text}\n${result.stdout}`, "error");
    }
  } catch (e) {
    appendDevLog(`Test execution failed: ${e.message}`, "error");
  }
}

// Promote tested script to active live display
async function promoteToLive() {
  if (!codeMirrorEditor) return;
  const code = codeMirrorEditor.getValue();
  // When promoting, promote DEV controls to become the active LIVE configuration
  const effect = document.getElementById("dev-select-effect").value;
  const interval_seconds = parseInt(document.getElementById("dev-input-interval").value, 10) || 30;
  const speed_ms = parseInt(document.getElementById("dev-input-speed").value, 10) || 40;
  const brightness = parseInt(document.getElementById("dev-select-brightness").value, 10) || 2;
  const font = document.getElementById("dev-select-font").value;
  const spacing = document.getElementById("dev-select-spacing").value;

  try {
    const res = await fetch("/api/script/promote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, interval_seconds, effect, speed_ms, brightness, font, spacing })
    });
    appendDevLog("Script and DEV parameters PROMOTED TO LIVE!", "system");
    appendLiveLog("New script and parameters promoted from Development!", "system");
  } catch (e) {
    appendDevLog(`Promotion failed: ${e.message}`, "error");
  }
}

// Reset script editor to template
function resetDefaultScript() {
  const defaultTemplate = `# DCLED Runtime Script
# Available: requests, re, time, datetime, math, json, read_file, get_json

def get_text():
    return "HELLO WORLD!"

get_text()
`;
  if (codeMirrorEditor) {
    codeMirrorEditor.setValue(defaultTemplate);
    clearEditorHighlights();
    appendDevLog("Reset script to template.", "system");
  }
}

async function clearLiveLogs() {
  document.getElementById("terminal-live").innerHTML = "";
  try {
    await fetch("/api/logs/clear", { method: "POST" });
  } catch (e) {
    console.error("Failed to clear backend logs", e);
  }
}

function clearDevLogs() {
  document.getElementById("terminal-dev").innerHTML = "";
}

function appendLiveLog(msg, type = "normal") {
  const term = document.getElementById("terminal-live");
  if (!term) return;
  const line = document.createElement("div");
  line.className = `log-entry ${type}`;
  line.innerText = `[${new Date().toTimeString().substring(0, 8)}] ${msg}`;
  term.appendChild(line);
  term.scrollTop = term.scrollHeight;
}

function appendDevLog(msg, type = "normal") {
  const term = document.getElementById("terminal-dev");
  if (!term) return;
  const line = document.createElement("div");
  line.className = `log-entry ${type}`;
  line.innerText = `[${new Date().toTimeString().substring(0, 8)}] ${msg}`;
  term.appendChild(line);
  term.scrollTop = term.scrollHeight;
}
