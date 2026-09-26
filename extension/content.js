// Mounts a subtitle overlay on top of the YouTube player, in time order from
// top to bottom: a short stack of up to ZH_MAX_LINES finished translations
// (each: the Japanese it came from, small, above its Chinese; see addZhLine),
// then the live Japanese line (partial while speaking, then the final) at the
// very bottom until that sentence's translation arrives and takes it over. See background.js for the JA_PARTIAL/JA_FINAL/
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
  // STT segment id of the final currently on the live JA line (null while it
  // shows a partial). Once a translation covering it arrives, the sentence is
  // in the stack with its Japanese, so the live line is cleared instead of
  // showing the same sentence twice.
  let liveFinalSegmentId = null;

  // Translation entries. A new translation no longer replaces the previous one
  // outright: with Sakura a short "啊" often arrived 0.5s after a long
  // sentence and wiped it before it could be read (14 of 75 lines in the
  // 09-26 live test). Each line gets a minimum display time from its length;
  // the newest line stays until a newer one arrives. At most 3 lines exist:
  // newest (full), second (full, slightly dimmer, fades once its time is up),
  // and the oldest, which starts fading as soon as it becomes third. A 4th
  // line removes the oldest immediately, so bursts of short lines can't pile up.
  // Each entry also shows its Japanese source, so a bad translation can be
  // checked against the original. A translation that covers the previous
  // entry's STT segments (server.py joins an unfinished sentence with the
  // next one) replaces that entry instead of repeating it on screen.
  const ZH_MAX_LINES = 3;
  const ZH_FADE_MS = 1200; // keep in sync with the zh-fade-out animation in styles.css
  let zhLines = []; // oldest first: { el, zhEl, srcEl, segments, expireAt, timer, fading }

  const zhMinDisplayMs = (text) => Math.min(5, Math.max(1.5, 1.5 + [...text].length * 0.08)) * 1000;

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
      existing.lastElementChild?.id === JA_LINE_ID &&
      document.getElementById(ZH_LINE_ID)
    ) {
      return existing;
    }
    if (existing) existing.remove();

    zhLines.forEach((line) => clearTimeout(line.timer));
    zhLines = []; // their elements went away with the old container

    const container = document.createElement("div");
    container.id = CONTAINER_ID;
    container.style.display = "none";

    const ja = document.createElement("div");
    ja.id = JA_LINE_ID;
    const zh = document.createElement("div");
    zh.id = ZH_LINE_ID;
    container.appendChild(zh);
    container.appendChild(ja);

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
    const hasContent = Boolean(ja?.textContent) || zhLines.length > 0;
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

  function removeZhLine(line) {
    clearTimeout(line.timer);
    line.el.remove();
    zhLines = zhLines.filter((l) => l !== line);
    updateContainerVisibility();
  }

  function fadeZhLine(line) {
    if (line.fading) return;
    line.fading = true;
    line.el.classList.remove("zh-second");
    line.el.classList.add("zh-fading");
    clearTimeout(line.timer);
    line.timer = setTimeout(() => removeZhLine(line), ZH_FADE_MS);
  }

  function addZhLine(text, sourceText, sourceSegments) {
    const zh = ensureOverlay() && document.getElementById(ZH_LINE_ID);
    if (!zh) {
      console.warn("[content] no player found, cannot show ZH line:", text);
      return;
    }
    const segments = Array.isArray(sourceSegments) ? sourceSegments : [];
    const overlaps = (line) => line.segments.some((id) => segments.includes(id));

    const newest = zhLines[zhLines.length - 1];
    if (newest && !newest.fading && overlaps(newest)) {
      // Joined translation of the newest entry's sentence: update it in place.
      newest.srcEl.textContent = sourceText || "";
      newest.zhEl.textContent = text;
      newest.segments = segments;
      newest.expireAt = Date.now() + zhMinDisplayMs(text);
      return;
    }
    zhLines.filter(overlaps).forEach(removeZhLine);
    while (zhLines.length >= ZH_MAX_LINES) removeZhLine(zhLines[0]);

    const el = document.createElement("div");
    el.className = "zh-entry zh-entering";
    const srcEl = document.createElement("div");
    srcEl.className = "zh-src";
    srcEl.textContent = sourceText || "";
    const zhEl = document.createElement("div");
    zhEl.className = "zh-line";
    zhEl.textContent = text;
    el.append(srcEl, zhEl);
    zh.appendChild(el);
    // A timer rather than requestAnimationFrame: rAF doesn't fire while the tab
    // is in the background, which would leave the entry invisible.
    setTimeout(() => el.classList.remove("zh-entering"), 30);

    const previous = zhLines[zhLines.length - 1];
    zhLines.push({ el, zhEl, srcEl, segments, expireAt: Date.now() + zhMinDisplayMs(text), timer: null, fading: false });
    if (previous && !previous.fading) {
      // No longer the newest: from now on it only stays for the rest of its minimum time.
      previous.el.classList.add("zh-second");
      previous.timer = setTimeout(() => fadeZhLine(previous), Math.max(0, previous.expireAt - Date.now()));
    }
    zhLines.slice(0, -2).forEach(fadeZhLine); // third line from the bottom starts fading right away
    updateContainerVisibility();
  }

  function clearZhLines() {
    zhLines.slice().forEach(removeZhLine);
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (message.target !== "content") return;

    if (message.type === "JA_PARTIAL") {
      // Live JA line shows "whatever is currently being said": the open
      // partial while mid-sentence, then the committed final (JA_FINAL below)
      // until its translation arrives.
      liveFinalSegmentId = null;
      setJaLine(message.text);
      console.log("[content] JA partial:", message.text);
    } else if (message.type === "JA_FINAL") {
      liveFinalSegmentId = message.segmentId;
      setJaLine(message.text);
      console.log(`[content] JA final #${message.segmentId}:`, message.text);
    } else if (message.type === "ZH_FINAL") {
      // The backend restarts unit numbering at 0 for every new session; never
      // let a previous session's higher number hide the new session's lines.
      if (message.segmentId === 0) lastDisplayedZhSegmentId = -1;
      if (message.segmentId != null && message.segmentId < lastDisplayedZhSegmentId) {
        console.warn(
          `[content] ignoring out-of-order ZH_FINAL #${message.segmentId} (already showing #${lastDisplayedZhSegmentId})`
        );
        return;
      }
      if (message.segmentId != null) lastDisplayedZhSegmentId = message.segmentId;
      // Deliberately NOT cleared by JA_PARTIAL updates, see addZhLine.
      addZhLine(message.text, message.sourceText, message.sourceSegments);
      if (liveFinalSegmentId != null && (message.sourceSegments || []).includes(liveFinalSegmentId)) {
        liveFinalSegmentId = null;
        setJaLine("");
      }
      console.log(`[content] ZH final #${message.segmentId} (for JA: ${message.sourceText}):`, message.text);
    } else if (message.type === "CLEAR") {
      liveFinalSegmentId = null;
      setJaLine("");
      clearZhLines();
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
