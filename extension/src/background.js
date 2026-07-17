/**
 * "Send to Yoink" — a minimal companion extension.
 *
 * It never downloads anything itself: on a context-menu click (or the toolbar
 * button) it hands the current page / link URL to the local Yoink desktop app
 * through the `yoink://download?url=<encoded>` deep link, which the app registered
 * with the OS. Yoink then focuses and analyzes it.
 *
 * The same file works as a Chromium service worker and a Firefox event-page
 * script — it only registers top-level `chrome.*` listeners, no DOM. The two
 * manifests differ solely in how they load this file (see manifest.*.json).
 */

const MENU_ID = "yoink-send";

// `chrome.*` exists in both Chromium and Firefox; `browser.*` is Firefox-only, so
// we stick to `chrome.*` for one cross-browser codebase.
const api = typeof browser !== "undefined" ? browser : chrome;

api.runtime.onInstalled.addListener(() => {
  api.contextMenus.create({
    id: MENU_ID,
    title: "Download with Yoink",
    contexts: ["page", "link", "video", "audio"],
  });
});

/**
 * Clean a target URL before sending it to Yoink.
 *
 * YouTube appends an auto-generated "Radio"/mix playlist to the address bar
 * (`&list=RD…&start_radio=1`) even when you just open a single video, which would
 * make Yoink treat one track as a whole playlist. Strip that auto-mix — but keep a
 * *real* playlist the user actually navigated to (`list=PL…`, `OLAK…`). Non-YouTube
 * URLs pass through untouched.
 */
function cleanTargetUrl(raw) {
  try {
    const u = new URL(raw);
    const host = u.hostname.replace(/^www\./, "");
    const isWatch =
      (host === "youtube.com" || host === "m.youtube.com") && u.searchParams.has("v");
    const isShort = host === "youtu.be";
    if (!isWatch && !isShort) return raw;
    const list = u.searchParams.get("list") || "";
    if (u.searchParams.has("start_radio") || /^RD/i.test(list)) {
      u.searchParams.delete("list");
      u.searchParams.delete("start_radio");
      u.searchParams.delete("index");
    }
    return u.toString();
  } catch {
    return raw; // not a parseable URL — send as-is
  }
}

/** Build the deep link and fire it from the given tab. */
function sendToYoink(tabId, targetUrl) {
  if (tabId == null || !targetUrl) return;
  const deepLink = "yoink://download?url=" + encodeURIComponent(cleanTargetUrl(targetUrl));

  // Navigating the active tab to a registered external scheme fires the OS handler
  // *without* leaving the page (the browser keeps the current document). This is
  // the cleanest UX — no throwaway tab. `activeTab` grants the injection when the
  // user invokes us (menu / button click).
  api.scripting
    .executeScript({
      target: { tabId },
      func: (url) => {
        window.location.href = url;
      },
      args: [deepLink],
    })
    .catch(() => {
      // Injection blocked (a restricted page: the New Tab page, the store, etc.).
      // Fall back to a background tab that fires the handler, then close it.
      api.tabs.create({ url: deepLink, active: false }, (tab) => {
        if (tab && tab.id != null) {
          setTimeout(() => api.tabs.remove(tab.id), 1500);
        }
      });
    });
}

// Right-click → "Download with Yoink": a link sends that link, anywhere else
// sends the current page (what yt-dlp wants — never a blob: media src).
api.contextMenus.onClicked.addListener((info, tab) => {
  sendToYoink(tab && tab.id, info.linkUrl || info.pageUrl || (tab && tab.url));
});

// Toolbar button: send the current tab's page.
api.action.onClicked.addListener((tab) => {
  sendToYoink(tab && tab.id, tab && tab.url);
});
