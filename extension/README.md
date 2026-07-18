# Send to Yoink — browser extension

A tiny companion extension. It **never downloads anything itself**: it hands the
current page (or a right-clicked link) to your local **Yoink** desktop app through
the `yoink://download?url=<encoded>` deep link that Yoink registers with the OS.
Yoink then focuses and analyzes it.

Because the download happens entirely in your own local app, the extension needs
only `contextMenus`, `activeTab` and `scripting` — no broad host access, no
network, no server.

## Install

| Browser | Store |
| --- | --- |
| Firefox / Zen / LibreWolf … | [Firefox Add-ons](https://addons.mozilla.org/firefox/addon/send-to-yoink/) |
| Chrome / Brave / Edge / Opera / Vivaldi … | [Chrome Web Store](https://chromewebstore.google.com/detail/ccbngfpojjboddajeialdgppooagdhkp) |

Prefer the stores — they auto-update. To install manually instead, grab the `.zip`
from the [`ext-latest`](https://github.com/ayozetr/yoink-app/releases/tag/ext-latest)
release and follow [*Load it*](#load-it-unsigned-for-testing) below.

Requires **[Yoink v3.0.0](https://github.com/ayozetr/yoink-app/releases/latest) or
newer** — that's the release that registers the `yoink://` link the extension fires.

## Layout

```
extension/
├── src/
│   ├── background.js        # shared logic (works as SW *and* event page)
│   └── icons/
├── manifest.firefox.json    # Firefox build (background.scripts + gecko id)
├── manifest.chromium.json   # Chromium build (background.service_worker)
└── build.sh                 # assembles dist/<browser>/ with manifest.json
```

`background.js` and the icons are **identical** across browsers. The **only**
difference between the two builds is the manifest — specifically the `background`
key (Firefox: `scripts`, Chromium: `service_worker`) and Firefox's
`browser_specific_settings.gecko` id.

## Build

```bash
./build.sh            # -> dist/firefox and dist/chromium
./build.sh firefox    # just one
```

## Load it (unsigned, for testing)

**Firefox** — temporary (until you restart Firefox):
1. `about:debugging#/runtime/this-firefox`
2. *Load Temporary Add-on…* → pick `dist/firefox/manifest.json`

**Chromium (Chrome/Brave/Edge)**:
1. `chrome://extensions`
2. Toggle *Developer mode* (top-right)
3. *Load unpacked* → pick the `dist/chromium/` folder

Prerequisite: the Yoink desktop app must be installed so the OS knows how to open
`yoink://` (the installer registers it; the dev app registers it at launch).

## Use

- **Right-click** a page, video, or link → **“Download with Yoink”**.
- Or click the **toolbar button** to send the current page.

The first time, the browser asks *“Open Yoink?”* — tick *always allow* to skip it
next time.

## Publishing

The extension is versioned and shipped **independently of the Yoink app releases** —
updating it never means re-cutting an app release. Bump `manifest.*.json` `version`
before each submit; once published, the store auto-updates users.

Three channels:

- **Firefox Add-ons store (AMO)** — the main install for Firefox / Zen (free).
- **Chrome Web Store** — the main install for Chromium (Chrome / Brave / Edge; $5 one-time).
- **Manual install (`ext-latest`)** — a rolling GitHub pre-release holding the raw
  `.zip`s at stable URLs, for loading unpacked (before a store listing exists, or for
  Zen / offline). This is what the app's **Settings ▸ Extension** tab links to.

### Firefox — Add-ons store (AMO, free)

1. Create an account at [addons.mozilla.org](https://addons.mozilla.org) → **Developer
   Hub** → **Manage API Keys** → generate an **issuer** + **secret**.
2. `cp .env.example .env` and fill `AMO_JWT_ISSUER` / `AMO_JWT_SECRET` (`.env` is
   git-ignored — never commit it).
3. Submit + sign in one command:
   ```bash
   ./build.sh publish-firefox        # AMO_CHANNEL=listed (public store) by default
   ```
   First submit creates the add-on; then fill the **listing** (name, summary,
   description, category, screenshots) on AMO and submit for review. Later submits
   just add a new version — one command, auto-updates everyone.

Suggested listing copy (keep it framed as a *bridge*, not a downloader):

> **Name:** Send to Yoink
> **Summary:** Right-click any page or link to send it to your local Yoink app. The
> extension never downloads anything itself — it just hands the URL to the app.
> **Privacy:** Collects no data. It only opens a `yoink://` link with the current
> page URL; nothing is sent anywhere but your own local app.

Needs `data_collection_permissions` (declared as `none`) and `strict_min_version`
≥ 142 — both already set in `manifest.firefox.json`.

### Chromium — Chrome Web Store ($5 one-time)

Listing: <https://chromewebstore.google.com/detail/ccbngfpojjboddajeialdgppooagdhkp>
(item id `ccbngfpojjboddajeialdgppooagdhkp` — permanent; the id-only URL redirects to
the slugged one).

Updates: upload a higher-versioned `dist/chromium` zip to the same item in the
Developer Dashboard. Can be scripted with `chrome-webstore-upload-cli` (needs a Google
Cloud OAuth client id/secret + refresh token).

Keep the listing framed as *"send links to your local Yoink app"* — Chrome is strict
about downloaders, and this extension does not download. The **single purpose**,
per-permission justifications and the "no data collected" disclosure are what the
review looks at; the privacy policy lives in [`PRIVACY.md`](PRIVACY.md).

### Manual install — the `ext-latest` channel

The app's **Settings ▸ Extension** tab (and its "download to load manually" link) point
at the `ext-latest` GitHub **pre-release** (`releases/tag/ext-latest`), which holds the
raw per-browser `.zip`s under **version-less** names, so the download URLs never change:

- `releases/download/ext-latest/send-to-yoink-firefox.zip`
- `releases/download/ext-latest/send-to-yoink-chromium.zip`

It is a **pre-release on purpose**: that keeps it out of `releases/latest`, so it cannot
interfere with the desktop app's auto-updater (which reads
`releases/latest/download/latest.json` — that must stay the newest *app* release).

Refresh it after an extension change with one command (`gh` required):

```bash
./build.sh publish-manual   # builds both + `gh release upload ext-latest … --clobber`
```

Because the asset names carry no version, this replaces the files in place — the app's
manual-install link keeps working with **no app change and no new app release**.

> First-time setup (already done): the pre-release was created with
> `gh release create ext-latest <zips> --prerelease --title "…" --notes-file …`. After
> that, only `publish-manual` is needed.
