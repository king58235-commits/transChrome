// Service worker: coordinates popup <-> offscreen document, owns tabCapture setup.

const OFFSCREEN_URL = "offscreen.html";

// capturing/backendConnected/activeTabId are NOT kept as plain variables here:
// the service worker is non-persistent and Chrome can suspend it after ~30s
// idle (the audio data path goes offscreen -> WebSocket -> Python directly, so
// background often has nothing to do for the whole session and gets
// suspended), which would wipe them. chrome.storage.session survives service
// worker restarts, so it's the source of truth; popup.js also reads it
// directly instead of asking background.
async function setState(partial) {
  await chrome.storage.session.set(partial);
  console.log("[background] storage.session updated", partial);
}

async function getState() {
  const result = await chrome.storage.session.get(["capturing", "backendConnected", "activeTabId"]);
  return {
    capturing: result.capturing ?? false,
    backendConnected: result.backendConnected ?? false,
    activeTabId: result.activeTabId ?? null,
  };
}

async function hasOffscreenDocument() {
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
  });
  return contexts.length > 0;
}

let creatingOffscreenDocument = null;

// Guards against two overlapping START_CAPTURE calls both passing the
// hasOffscreenDocument() check before either createDocument() call resolves,
// which would throw "Only a single offscreen document may be created".
async function ensureOffscreenDocument() {
  if (await hasOffscreenDocument()) return;

  if (!creatingOffscreenDocument) {
    creatingOffscreenDocument = chrome.offscreen
      .createDocument({
        url: OFFSCREEN_URL,
        reasons: ["USER_MEDIA"],
        justification: "Capture YouTube tab audio and stream it to the local STT backend.",
      })
      .finally(() => {
        creatingOffscreenDocument = null;
      });
  }
  await creatingOffscreenDocument;
}

function sendToOffscreen(message) {
  console.log("[background] -> offscreen", message);
  // target must come after the spread: a relayed message (e.g. one that
  // originated elsewhere) may already carry its own `target` key, which
  // would otherwise silently override the one we intend here.
  chrome.runtime.sendMessage({ ...message, target: "offscreen" }).catch((err) => {
    console.error("[background] sendMessage to offscreen failed", err, message);
  });
}

function sendToPopup(message) {
  console.log("[background] -> popup", message);
  chrome.runtime.sendMessage({ ...message, target: "popup" }).catch((err) => {
    // Expected/benign when no popup is currently open to receive it.
    console.log("[background] sendMessage to popup had no receiver (popup closed?)", err.message);
  });
}

async function startCapture() {
  console.log("[background] startCapture requested");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) {
    console.error("[background] no active tab found");
    sendToPopup({ type: "ERROR", message: "找不到目前的分頁" });
    return;
  }
  if (!/^https?:\/\/(www\.)?youtube\.com\//.test(tab.url || "")) {
    console.error("[background] active tab is not YouTube", tab.url);
    sendToPopup({ type: "ERROR", message: "請在 YouTube 分頁上使用" });
    return;
  }

  await setState({ activeTabId: tab.id });

  // No consumerTabId: the call originates from the service worker (an extension
  // context), so the returned stream ID is scoped for use by the extension itself
  // (the offscreen document), not by a frame inside the target tab. Passing
  // consumerTabId here would scope it to the tab instead and getUserMedia in the
  // offscreen document would fail to redeem it.
  let streamId;
  try {
    streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
    console.log("[background] got streamId", streamId, "for tab", tab.id);
  } catch (err) {
    console.error("[background] getMediaStreamId failed", err);
    sendToPopup({ type: "ERROR", message: `tabCapture 失敗: ${err.message}` });
    return;
  }

  await ensureOffscreenDocument();
  console.log("[background] offscreen document ready");
  sendToOffscreen({ type: "start-capture", streamId });
  await setState({ capturing: true });
  sendToPopup({ type: "STATUS", capturing: true });
}

async function stopCapture() {
  console.log("[background] stopCapture requested");
  sendToOffscreen({ type: "stop-capture" });
  await sendToContent({ type: "CLEAR" }); // clear any subtitles left on screen from before stopping
  await setState({ capturing: false, backendConnected: false, activeTabId: null });
  sendToPopup({ type: "STATUS", capturing: false });
}

async function sendToContent(message) {
  const { activeTabId } = await getState();
  if (activeTabId == null) {
    console.warn("[background] tried to message content script but no activeTabId set", message);
    return;
  }
  const full = { ...message, target: "content" };
  try {
    await chrome.tabs.sendMessage(activeTabId, full);
  } catch (err) {
    // No content script listening in that tab: either the tab was already open
    // before this extension (re)loaded (a manifest content_scripts injection
    // only happens on a fresh page load, not on an extension reload), or the
    // page navigated somewhere the content script isn't declared for. Inject
    // it now and retry once, instead of silently dropping the subtitle.
    console.warn("[background] content script unreachable, injecting and retrying", err.message);
    try {
      await chrome.scripting.executeScript({ target: { tabId: activeTabId }, files: ["content.js"] });
      await chrome.scripting.insertCSS({ target: { tabId: activeTabId }, files: ["styles.css"] });
      await chrome.tabs.sendMessage(activeTabId, full);
    } catch (retryErr) {
      console.error("[background] sendMessage to content script failed after re-injection", retryErr);
      if (String(retryErr.message).includes("No tab with id")) {
        // The tab itself is gone (closed/navigated away entirely), not just a
        // missing content script — retrying on every future message would
        // just repeat this same failure. Clear the stale reference instead.
        console.warn("[background] target tab no longer exists, clearing activeTabId");
        await setState({ activeTabId: null });
      }
    }
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.target !== "background") return;
  console.log("[background] received message", message, "from", sender.url || sender.id);

  if (message.type === "START_CAPTURE") {
    startCapture();
  } else if (message.type === "STOP_CAPTURE") {
    stopCapture();
  } else if (message.type === "GET_STATUS") {
    getState().then((state) => {
      console.log("[background] GET_STATUS ->", state);
      sendResponse(state);
    });
    return true; // keep the message channel open for the async sendResponse above
  } else if (message.type === "BACKEND_STATUS") {
    // Await before resolving so the service worker isn't recycled mid-write,
    // and to keep the sender's message port open until the write is durable.
    setState({ backendConnected: message.connected }).then(() => sendResponse({ ok: true }));
    sendToPopup(message);
    return true;
  } else if (message.type === "ERROR") {
    sendToPopup(message);
  } else if (message.type === "JA_PARTIAL") {
    sendToContent({ type: "JA_PARTIAL", text: message.text });
  } else if (message.type === "JA_FINAL") {
    sendToContent({ type: "JA_FINAL", segmentId: message.segmentId, text: message.text });
  } else if (message.type === "ZH_FINAL") {
    sendToContent({
      type: "ZH_FINAL",
      segmentId: message.segmentId,
      sourceText: message.sourceText,
      text: message.text,
    });
  }
});

console.log("[background] service worker started");
