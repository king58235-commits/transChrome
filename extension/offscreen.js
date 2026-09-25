// Runs in the offscreen document: has DOM access for getUserMedia / Web Audio,
// which the MV3 service worker (background.js) does not have.

const BACKEND_URL = "ws://127.0.0.1:8765";

let mediaStream = null;
let audioContext = null;
let sourceNode = null;
let workletNode = null;
let ws = null;

function notifyBackground(message) {
  console.log("[offscreen] -> background", message);
  // target after the spread, same reasoning as background.js's sendToPopup/sendToOffscreen.
  chrome.runtime.sendMessage({ ...message, target: "background" }).catch((err) => {
    console.error("[offscreen] sendMessage to background failed", err, message);
  });
}

let audioChunkCount = 0;

function connectWebSocket() {
  console.log("[offscreen] WebSocket connecting to", BACKEND_URL);
  ws = new WebSocket(BACKEND_URL);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    console.log("[offscreen] WebSocket open");
    audioChunkCount = 0;
    ws.send(JSON.stringify({ type: "start" }));
    notifyBackground({ type: "BACKEND_STATUS", connected: true });
  };
  ws.onclose = (event) => {
    console.log("[offscreen] WebSocket closed", { code: event.code, reason: event.reason });
    notifyBackground({ type: "BACKEND_STATUS", connected: false });
  };
  ws.onerror = (event) => {
    console.error("[offscreen] WebSocket error", event);
    notifyBackground({ type: "ERROR", message: "無法連接本機字幕服務 (localhost:8765)" });
  };
  ws.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (err) {
      console.error("[offscreen] failed to parse backend message", err, event.data);
      return;
    }
    if (data.type === "partial") {
      console.log("[offscreen] partial:", data.text);
      notifyBackground({ type: "JA_PARTIAL", text: data.text });
    } else if (data.type === "final") {
      console.log(`[offscreen] final #${data.segment_id}:`, data.text);
      notifyBackground({ type: "JA_FINAL", segmentId: data.segment_id, text: data.text });
    } else if (data.type === "translation") {
      console.log(`[offscreen] translation #${data.segment_id}:`, data.text);
      notifyBackground({
        type: "ZH_FINAL",
        segmentId: data.segment_id,
        sourceText: data.source_text,
        text: data.text,
      });
    }
  };
}

async function startCapture(streamId) {
  console.log("[offscreen] startCapture", { streamId });
  if (audioContext) {
    console.log("[offscreen] capture already active, tearing down first");
    // A capture is already active; tear it down before starting a new one
    // instead of leaking the old mediaStream/audioContext.
    await stopCapture();
  }

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
        },
      },
      video: false,
    });
    console.log("[offscreen] getUserMedia OK", mediaStream.getAudioTracks());
  } catch (err) {
    console.error("[offscreen] getUserMedia failed", err);
    notifyBackground({ type: "ERROR", message: `取得分頁音訊失敗: ${err.message}` });
    return;
  }

  audioContext = new AudioContext();
  sourceNode = audioContext.createMediaStreamSource(mediaStream);

  // Route back to the speakers so tabCapture doesn't silence the tab for the user.
  sourceNode.connect(audioContext.destination);

  try {
    await audioContext.audioWorklet.addModule(chrome.runtime.getURL("worklet-processor.js"));
    console.log("[offscreen] AudioWorklet module loaded");
  } catch (err) {
    console.error("[offscreen] AudioWorklet addModule failed", err);
    notifyBackground({ type: "ERROR", message: `載入 AudioWorklet 失敗: ${err.message}` });
    return;
  }

  workletNode = new AudioWorkletNode(audioContext, "downsample-processor", {
    processorOptions: { targetSampleRate: 16000 },
  });

  // Keep the worklet node in the active audio graph without producing audible output.
  const silentGain = audioContext.createGain();
  silentGain.gain.value = 0;
  sourceNode.connect(workletNode);
  workletNode.connect(silentGain).connect(audioContext.destination);

  workletNode.port.onmessage = (event) => {
    audioChunkCount += 1;
    if (audioChunkCount % 20 === 1) {
      console.log("[offscreen] audio chunk", audioChunkCount, "wsState", ws && ws.readyState);
    }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(event.data);
    }
  };

  connectWebSocket();

  mediaStream.getAudioTracks()[0].addEventListener("ended", () => {
    console.warn("[offscreen] audio track ended");
    notifyBackground({ type: "ERROR", message: "音訊串流已結束（分頁可能已關閉）" });
    stopCapture();
  });
}

async function stopCapture() {
  console.log("[offscreen] stopCapture");
  if (ws) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
    }
    ws.close();
    ws = null;
  }
  if (workletNode) {
    workletNode.disconnect();
    workletNode = null;
  }
  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  if (audioContext) {
    await audioContext.close();
    audioContext = null;
  }
}

console.log("[offscreen] document loaded, listener registered");

chrome.runtime.onMessage.addListener((message) => {
  if (message.target !== "offscreen") return;
  console.log("[offscreen] received message", message);
  if (message.type === "start-capture") {
    startCapture(message.streamId);
  } else if (message.type === "stop-capture") {
    stopCapture();
  }
});
