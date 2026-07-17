# Send to Yoink — browser extension

A tiny companion extension. It **never downloads anything itself**: it hands the
current page (or a right-clicked link) to your local **Yoink** desktop app through
the `yoink://download?url=<encoded>` deep link that Yoink registers with the OS.
Yoink then focuses and analyzes it.

Because the download happens entirely in your own local app, the extension needs
only `contextMenus`, `activeTab` and `scripting` — no broad host access, no
network, no server.

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

## Publishing (later)

- **Firefox (AMO)** is free and permissive; Mozilla can also sign a self-hosted
  `.xpi` you distribute yourself.
- **Chromium**: the Chrome Web Store charges a one-time $5 developer fee and is
  strict about downloaders — keep the listing framed as *“send links to your local
  Yoink app”*, since the extension itself does not download.
