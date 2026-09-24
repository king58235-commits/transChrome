const toggleBtn = document.getElementById("toggle-btn");
const backendStatusEl = document.getElementById("backend-status");
const subtitleStatusEl = document.getElementById("subtitle-status");
const errorBox = document.getElementById("error-box");

let capturing = false;

function setCapturing(value) {
  capturing = value;
  toggleBtn.textContent = capturing ? "停止字幕" : "開始字幕";
  subtitleStatusEl.textContent = capturing ? "Running" : "Stopped";
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

toggleBtn.addEventListener("click", () => {
  errorBox.hidden = true;
  chrome.runtime.sendMessage({
    target: "background",
    type: capturing ? "STOP_CAPTURE" : "START_CAPTURE",
  });
});

// Read directly from chrome.storage.session rather than asking the (possibly
// suspended) service worker — storage survives its restarts and this avoids
// any dependency on it waking up in time.
chrome.storage.session.get(["capturing", "backendConnected"], (result) => {
  console.log("[popup] initial storage.session read", result, chrome.runtime.lastError);
  setCapturing(result.capturing ?? false);
  backendStatusEl.textContent = result.backendConnected ? "Connected" : "Disconnected";
});

chrome.runtime.onMessage.addListener((message) => {
  if (message.target !== "popup") return;
  console.log("[popup] received message", message);
  if (message.type === "STATUS") {
    setCapturing(message.capturing);
  } else if (message.type === "BACKEND_STATUS") {
    backendStatusEl.textContent = message.connected ? "Connected" : "Disconnected";
  } else if (message.type === "ERROR") {
    showError(message.message);
  }
});
