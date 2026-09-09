# Zero-config PO tokens — minting in the WebView

**Status:** Phases 1–2 shipped **and validated live** (2026-09-09) — a real
per-video PO token was minted end-to-end in the packaged AppImage against live
YouTube (backend → WebView → `bgutils-js` → proxied Google attestation → token,
~1 s). `auto` still ships **opt-in** (default `manual`): the flow depends on
YouTube-internal BotGuard details that change, so it's gated rather than default.

**Architecture:** the app's **existing** WebView runs `bgutils-js`; its network
(the BotGuard Create / GenerateIT calls) is routed through the backend's
`/api/po-token/proxy`, so the WebView only ever *connects* to `127.0.0.1` — no
second WebView window is needed. The hand-off is the broker in
`services/po_token_bridge.py` + the `/api/po-token/*` routes; the minter loop is
`src/lib/poTokenMinter.ts`.

**The one CSP relaxation — `script-src 'unsafe-eval'`.** Proxying the network
covered `connect-src`, but BotGuard's interpreter runs via `new Function(...)`,
which the app CSP's `script-src 'self'` blocked (live testing surfaced the exact
`EvalError`). A sandboxed iframe can't help — a child frame's CSP can only
*narrow* the parent's, so it can't regain `eval`. So enabling auto-PO required
adding `'unsafe-eval'` to the app's `script-src`. **Tradeoff:** eval is now
allowed app-wide and Google's BotGuard code runs in the main window's context.
The practical risk here is low — the frontend is fully bundled/trusted, the only
remote content rendered (GitHub release-note markdown) is scheme-sanitised, and
the proxied Google traffic is HTTPS-pinned — but a fully-isolated
**hidden WebView window** (its own relaxed CSP, no app access) remains the
stronger long-term option if the eval surface is ever a concern.

## Why

YouTube increasingly answers extraction with a *"Sign in to confirm you're not a
bot"* wall. A **PO (proof-of-origin) token** clears it without cookies. The
existing opt-in setting (`po_token`) makes the user mint one *by hand* and paste
it — but per the [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide),
web GVS/Player tokens are now **bound to the video id**, so a single pasted token
is of limited use: you need a *fresh token per video*.

The goal is to mint them automatically, **reusing the app's existing WebView**
(webkit2gtk on Linux, WebView2 on Windows) as the JavaScript runtime — so
**nothing extra is bundled** (~0 MB, vs ~100 MB for a Deno/Node runtime), which
keeps the app small and launch fast.

## Spike result (2026-08-30): feasible

Confirmed in a real browser that the mechanism BotGuard relies on works:

- `new Function(...)` (the BotGuard VM's execution primitive) runs.
- The challenge (`interpreterUrl` / `globalName` / `program`) is embedded in the
  youtube.com HTML (`window.ytAtN`).
- `VISITOR_DATA` is readable from `ytcfg`.

The official [`bgutils-js`](https://github.com/LuanRT/BgUtils) example already
runs the **full** mint under **jsdom** (a *fake* DOM in Node). A real WebView (a
*real* DOM, with web security relaxed for our own page) runs it at least as well.
The CSP/CORS restrictions seen when testing *on* youtube.com do **not** apply to
our own security-relaxed WebView page.

## The mint flow (bgutils-js v4.0.3)

1. Fetch the youtube.com HTML → extract the BotGuard challenge + `visitor_data`.
2. Load the interpreter VM (`new Function`).
3. `BotGuardClient.snapshot()` → a BotGuard attestation.
4. POST it to `GenerateIT` → an **integrity token** (cache it; valid ~hours,
   video-independent).
5. `WebPoMinter` → `mintAsWebsafeString(videoId)` → the **per-video** token
   (local, no network — derived from the cached integrity token).

The expensive, networked steps (1–4) happen **once per few hours**; step 5 is
cheap and runs per video.

## Architecture — the bridge

yt-dlp runs in the Python backend, on a worker thread, and wants a PO token
*synchronously* while extracting/downloading. The JS runtime is the frontend's
WebView. So a token request has to cross three boundaries:

```
yt-dlp (backend thread)
   │  needs a PO token for (context, video_id)
   ▼
GetPOT provider  (Python, registered as a yt-dlp plugin)   ← Phase 3
   │  request mint(video_id)
   ▼
Tauri command / IPC  (Rust)                                ← Phase 2
   │  emit "po-token:mint" { video_id }  → hidden WebView
   ▼
hidden WebView  (bgutils-js)                               ← Phase 2
   │  cache the integrity token; mintAsWebsafeString(video_id)
   ▼
returns the minted token back up the same chain
```

### Backend seam (Phase 1 — done)

`backend/app/services/po_token.py` owns the mode logic and a per-video token
cache:

- `resolve_tokens(video_id)` returns the token(s) to hand yt-dlp, per
  `settings.po_token_mode`:
  - `off` → none.
  - `manual` → the pasted `po_token` (the classic path — unchanged behaviour).
  - `auto` → a minted per-video token when available, else the pasted token as a
    fallback (so the **headless CLI**, which has no WebView, still works with a
    manual token).
- `mint(video_id)` caches minted tokens (`_TOKEN_TTL_SECONDS`, well under their
  real lifetime) so repeated extractor calls for one video don't each round-trip.
- **`_mint_via_webview(video_id)` is the seam.** It returns `None` today, so
  `auto` degrades gracefully instead of failing a download. Phases 2–3 make it
  actually reach the WebView.

`core/ytdlp_options.py::network_options()` already sources its token through
`resolve_tokens()` (no `video_id` at that layer, so it only yields the manual /
off tokens; the per-video path is driven by the provider below).

### Phase 2 — the WebView + Rust bridge

- A hidden Tauri WebView (or a hidden `<iframe>`/worker inside the main one) with
  web security relaxed, loading a small local page that bundles `bgutils-js` (a
  few KB) — **no external script** (respects our CSP; nothing is fetched from a
  CDN except the youtube.com HTML/interpreter the flow itself fetches).
- A Tauri command the backend can call (over the existing local IPC, or a tiny
  loopback endpoint the WebView long-polls) that asks the page to mint a token
  for a `video_id` and returns it.
- The page keeps the **integrity token** cached in JS and re-attests only when it
  expires.

### Phase 3 — the yt-dlp GetPOT provider

- Register a [`GetPOT`](https://github.com/coletdjnz/yt-dlp-get-pot) provider
  plugin so yt-dlp requests a token per `(client, context, video_id)` and we mint
  on demand via `po_token.mint(video_id)` → the bridge. This is the *correct*
  integration point (yt-dlp hands us the real request context), replacing the
  static `extractor_args` injection for `auto` mode.

## Settings

`po_token_mode` (`off` / `manual` / `auto`), persisted like every other setting,
with the manual `po_token` field kept as the fallback source. Default is
`manual` so existing behaviour is unchanged; **`auto` stays opt-in** until the
bridge is tested against real YouTube responses.

## Caveats

- **GUI-only minting.** Minting each per-video token needs the JS runtime, so
  auto-PO is fundamentally a **desktop-GUI** feature. The headless CLI has no
  WebView and falls back to a manual token / cookies (or, later, could mint via a
  running GUI's backend).
- Gate `auto` behind real-world testing before making it the default — YouTube's
  challenge shape changes, and bgutils-js tracks it, so pin a known-good version
  and watch for breakage.
