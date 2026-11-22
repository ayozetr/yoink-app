# Zero-config PO tokens — minting in the WebView

> **Note (egui port):** this document describes the original design, when the
> token was minted inside the React app's WebView via `poTokenMinter.ts`. In the
> egui app the minter is a **separate helper process** — the `desktop-minter`
> crate (`yoink-minter`), a hidden WebView the desktop app spawns and supervises
> (`desktop/src/minter.rs`) only while `po_token_mode` is `auto`. The backend
> bridge, the SSRF-scoped proxy and the `bgutils-js` flow below are unchanged.

**Status:** shipped **and validated live** (2026-09-15) — a real **session** GVS
PO token was minted end-to-end (backend → WebView → `bgutils-js` → proxied Google
attestation → token, ~1 s) and, crucially, **verified to work against live
YouTube**: with the minted token + its `visitor_data`, the `mweb` client returned
**26** downloadable GVS video formats (a range-GET of a picked format returned
`206`), versus **1** without it. This also surfaced the binding fix below. The
backend side was later ported to native Rust (`backend-rs/src/po_token.rs`) with the same
contract and the frontend minter unchanged.

**Two things the live test corrected:**
1. **Binding.** The web GVS token is bound to the session **`visitor_data`** when
   logged out (not the video id — that only applies under YouTube's
   `html5_generate_content_po_token` experiment). So we mint **once per session**
   against a `visitor_data` fetched from youtube.com and hand yt-dlp **both** the
   token and that same `visitor_data`, or yt-dlp rejects it.
2. **Client.** The logged-out default clients are `visionos` + `web`, but `web`
   degrades to *images-only* when logged out, so a `web.gvs` token has no formats
   to authorize. The client that reliably yields the GVS-gated formats is
   **`mweb`**, so `auto` hands the token to the web-based clients (`mweb`, `web`,
   `web_safari`, `web_embedded`) **and** adds `mweb` to `player_client`.

`auto` ships **opt-in** (default `manual`): the flow depends on YouTube-internal
BotGuard details that change, so it's gated rather than default.

**Architecture:** the app's **existing** WebView runs `bgutils-js`; its network
(the BotGuard Create / GenerateIT calls) is routed through the backend's
`/api/po-token/proxy`, so the WebView only ever *connects* to `127.0.0.1` — no
second WebView window is needed. The hand-off is the broker in
`backend-rs/src/po_token.rs` + the `/api/po-token/*` routes; the minter loop is
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
a web GVS token is **bound to the session `visitor_data`** (when logged out), and
the matching `visitor_data` has to be passed to yt-dlp alongside it — fiddly to
do by hand, and the token has to be re-minted when the session rotates.

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
5. `WebPoMinter` → `mintAsWebsafeString(visitorData)` → the **session** token
   (local, no network — derived from the cached integrity token, bound to the
   `visitor_data` from step 1).

The expensive, networked steps (1–4) happen **once per few hours**; step 5 is
cheap. Because the binding is the session `visitor_data` (not the video), the
minted token is reused across every video in the session.

## Architecture — the bridge

yt-dlp runs as a child process spawned by the native Rust backend, and a download
in `auto` mode wants a PO token *before* the child starts. The JS runtime is the
frontend's WebView. So a token request has to cross three boundaries (the backend
side `await`s it — no thread blocks):

```
execute_download (backend task, per download)
   │  po_token::download_extractor_args(url).await  → mint_session()
   ▼
broker().submit_mint(timeout).await   (src/po_token.rs)
   │  enqueue a job; await the result (with a timeout) via a oneshot channel
   ▼
GET /api/po-token/pending  ← long-polled by the WebView loop
   │  { id }
   ▼
WebView loop  (src/lib/poTokenMinter.ts, bgutils-js)
   │  fetch visitor_data + mint; bgutils network via POST /api/po-token/proxy
   ▼
POST /api/po-token/result  { id, token, visitor_data }
   ▼
broker unblocks submit_mint → { token, visitor_data }, cached for the session
```

### Backend seam (`src/po_token.rs`)

One module owns the mode logic, the broker, and a **session** token cache (one
`(token, visitor_data)` pair, `TOKEN_TTL` under its real lifetime):

- `info_extractor_args(settings)` — the manual/off token(s) injected into every
  metadata/search `-J` call (no URL at that layer, so it never mints): `off` →
  none; `manual`/`auto` → the pasted token(s).
- `download_extractor_args(url, settings)` — the per-download path. On a YouTube
  URL in `auto` mode it mints the session token (once, cached) and returns the
  `youtube` extractor-args value: `player_client=default,mweb`, the
  `<client>.gvs+<token>` list for the web-based clients, and the bound
  `visitor_data` — plus any manual tokens. Otherwise it's the manual token(s)
  passthrough, and `None` for off / non-YouTube.
- `mint_session()` → `mint_via_webview()` — submits a mint job to the broker and
  awaits (bounded) the WebView's answer. Returns `None` when no WebView is polling
  (the **headless CLI**) or during a post-failure backoff, so `auto` degrades to
  the manual token / cookies instead of failing.

`execute_download` appends `download_extractor_args(url)` as a `--extractor-args`
argument; `run_ytdlp_json` (metadata/search) appends `info_extractor_args`. The
broker is an in-process singleton (`tokio::sync` `oneshot` + `Notify`), reached
the same way from the axum handlers and the download task.

### The WebView bridge

- The **existing** main WebView runs `poTokenMinter.ts` (started from `App.tsx`
  only in `auto` mode, desktop-only) — no hidden window. It long-polls
  `/api/po-token/pending`, mints with `bgutils-js`, and POSTs the result.
- `bgutils`'s own network (BotGuard Create / GenerateIT, the youtube.com HTML)
  goes through `POST /api/po-token/proxy` — SSRF-pinned and scoped to Google
  hosts — so the WebView only ever *connects* to `127.0.0.1`.
- The **integrity token** and `visitor_data` are cached in JS; only a mint
  failure forces re-attestation.

## Settings

`po_token_mode` (`off` / `manual` / `auto`), persisted like every other setting,
with the manual `po_token` field kept as the fallback source. Default is
`manual` so existing behaviour is unchanged; **`auto` stays opt-in** until the
flow is battle-tested across YouTube changes.

## Caveats

- **GUI-only minting.** Minting needs the JS runtime, so auto-PO is fundamentally
  a **desktop-GUI** feature. The headless CLI has no WebView and falls back to a
  manual token / cookies.
- **Client/binding track YouTube.** Both the `visitor_data` binding and the
  `mweb`-is-the-working-client finding reflect YouTube's *current* logged-out
  behaviour; the default clients and which one yields GVS formats can shift, so
  watch for breakage and keep `bgutils-js` pinned to a known-good version.
