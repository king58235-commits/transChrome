// Mounts a two-line subtitle overlay on top of the YouTube player: Japanese
// (partial while speaking, replaced by final once a sentence commits) on top,
// Traditional Chinese translation (final only, stays until replaced by the
// next translation) below. See background.js for the JA_PARTIAL/JA_FINAL/
// ZH_FINAL message types this listens for.

// Idempotency guard: background.js can re-inject this file via
// chrome.scripting.executeScript when a plain sendMessage finds no listener
// (see its comment on that retry path). MV3 content scripts run in a
// per-tab isolated world that PERSISTS across such re-injections, so a
// second run's top-level `const`/`let` would collide with the first run's
// and throw "Identifier has already been declared", aborting the whole
// script. Wrapping everything below in this check keeps all declarations
// block-scoped (not script-level) and makes re-injection a harmless no-op.
if (!window.__ytJpSubtitleContentLoaded) {
  window.__ytJpSubtitleContentLoaded = true;

  const CONTAINER_ID = "yt-jp-subtitle-overlay";
  const JA_LINE_ID = "yt-jp-subtitle-overlay-ja";
  const ZH_LINE_ID = "yt-jp-subtitle-overlay-zh";

  // Defensive ordering guard (translations should already arrive in order
  // from the backend's single FIFO worker, but never let a stale one
  // overwrite a newer one on screen).
  let lastDisplayedZhSegmentId = -1;

  const findPlayerContainer = () =>
    document.querySelector("#movie_player") || document.querySelector(".html5-video-player");

  function ensureOverlay() {
    const player = findPlayerContainer();
    if (!player) return null;

    const existing = document.getElementById(CONTAINER_ID);
    // Only adopt an existing container if it's still attached under the
    // current player AND actually has the JA/ZH child lines this version
    // expects — an older content.js (e.g. from before the two-line
    // redesign) could have left behind a container missing that structure,
    // which previously caused getElementById(JA_LINE_ID) to return null.
    if (
      existing &&
      player.contains(existing) &&
      document.getElementById(JA_LINE_ID) &&
      document.getElementById(ZH_LINE_ID)
    ) {
      return existing;
    }
    if (existing) existing.remove();

    const container = document.createElement("div");
    container.id = CONTAINER_ID;
    container.style.display = "none";

    const ja = document.createElement("div");
    ja.id = JA_LINE_ID;
    const zh = document.createElement("div");
    zh.id = ZH_LINE_ID;
    container.appendChild(ja);
    container.appendChild(zh);

    if (getComputedStyle(player).position === "static") {
      player.style.position = "relative";
    }
    player.appendChild(container);
    console.log("[content] overlay mounted");
    return container;
  }

  function updateContainerVisibility() {
    const container = document.getElementById(CONTAINER_ID);
    if (!container) return;
    const ja = document.getElementById(JA_LINE_ID);
    const zh = document.getElementById(ZH_LINE_ID);
    const hasContent = Boolean(ja?.textContent) || Boolean(zh?.textContent);
    container.style.display = hasContent ? "flex" : "none";
  }

  function setJaLine(text) {
    if (!ensureOverlay()) {
      console.warn("[content] no player found, cannot show JA line:", text);
      return;
    }
    document.getElementById(JA_LINE_ID).textContent = text;
    updateContainerVisibility();
  }

  function setZhLine(text) {
    if (!ensureOverlay()) {
      console.warn("[content] no player found, cannot show ZH line:", text);
      return;
    }
    document.getElementById(ZH_LINE_ID).textContent = text;
    updateContainerVisibility();
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (message.target !== "content") return;

    if (message.type === "JA_PARTIAL") {
      // JA line always shows "whatever is currently happening" — the open
      // partial while mid-sentence, or the committed final right after (a new
      // partial cycle only starts once the buffer clears post-finalize), so no
      // separate branch is needed for JA_FINAL below.
      setJaLine(message.text);
      console.log("[content] JA partial:", message.text);
    } else if (message.type === "JA_FINAL") {
      setJaLine(message.text);
      console.log(`[content] JA final #${message.segmentId}:`, message.text);
    } else if (message.type === "ZH_FINAL") {
      if (message.segmentId != null && message.segmentId < lastDisplayedZhSegmentId) {
        console.warn(
          `[content] ignoring out-of-order ZH_FINAL #${message.segmentId} (already showing #${lastDisplayedZhSegmentId})`
        );
        return;
      }
      if (message.segmentId != null) lastDisplayedZhSegmentId = message.segmentId;
      // Deliberately NOT cleared by JA_PARTIAL updates — stays on screen,
      // giving a reasonable reading time, until the next ZH_FINAL replaces it.
      setZhLine(message.text);
      console.log(`[content] ZH final #${message.segmentId} (for JA: ${message.sourceText}):`, message.text);
    } else if (message.type === "CLEAR") {
      setJaLine("");
      setZhLine("");
      lastDisplayedZhSegmentId = -1;
    }
  });

  // YouTube is a SPA; re-mount the overlay whenever navigation swaps the player.
  document.addEventListener("yt-navigate-finish", () => ensureOverlay());
  new MutationObserver(() => ensureOverlay()).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  ensureOverlay();
}
