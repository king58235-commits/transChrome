// Mounts the subtitle overlay on top of the YouTube player.
// Subtitle text updates are wired up in a later stage (once STT is connected);
// for now this only proves the overlay can be mounted and survives SPA navigation.

const OVERLAY_ID = "yt-jp-subtitle-overlay";

function findPlayerContainer() {
  return document.querySelector("#movie_player") || document.querySelector(".html5-video-player");
}

function ensureOverlay() {
  const player = findPlayerContainer();
  if (!player) return null;

  let overlay = document.getElementById(OVERLAY_ID);
  if (overlay && player.contains(overlay)) return overlay;

  overlay = document.createElement("div");
  overlay.id = OVERLAY_ID;
  overlay.textContent = "";
  overlay.style.display = "none"; // no padding/background box until there's real text

  if (getComputedStyle(player).position === "static") {
    player.style.position = "relative";
  }
  player.appendChild(overlay);
  console.log("[content] overlay mounted");
  return overlay;
}

function setSubtitleText(text, final) {
  const overlay = ensureOverlay();
  if (!overlay) {
    console.warn("[content] no player found, cannot show subtitle:", text);
    return;
  }
  overlay.textContent = text;
  // Hide the box entirely when empty, not just the text — otherwise the
  // padding/background still render as a lingering empty rounded rectangle.
  overlay.style.display = text ? "block" : "none";
  console.log(`[content] subtitle updated (${final ? "final" : "partial"}):`, text);
}

chrome.runtime.onMessage.addListener((message) => {
  if (message.target !== "content") return;
  if (message.type === "SUBTITLE_UPDATE") {
    setSubtitleText(message.text, message.final);
  }
});

// YouTube is a SPA; re-mount the overlay whenever navigation swaps the player.
document.addEventListener("yt-navigate-finish", () => ensureOverlay());
new MutationObserver(() => ensureOverlay()).observe(document.documentElement, {
  childList: true,
  subtree: true,
});

ensureOverlay();
