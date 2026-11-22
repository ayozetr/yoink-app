# Desktop app

The native desktop UI (`desktop/`), built with **Rust + egui/eframe**. It is a
REST/WebSocket client of the local `yoink-core` backend, which it spawns and
supervises on startup, so the whole thing is one self-contained program.

## Structure

```
desktop/
├── Cargo.toml
├── assets/                 # bundled fonts (Gloock, Inter, Inter SemiBold) + icon
├── packaging/
│   └── yoink.desktop       # AppImage desktop entry (registers yoink:// + the icon)
└── src/
    ├── main.rs             # eframe bootstrap, window/viewport, single-instance
    ├── app.rs              # the App struct: all screen state + per-tab UI
    │                       #   (Inicio / Cola / Historial / Ajustes / Registro),
    │                       #   modals, the update banner, the custom title bar
    ├── api.rs              # the backend worker thread (own tokio runtime): Cmd/Evt
    │                       #   channels, REST + the download WebSocket, the in-place
    │                       #   self-update (download + minisign verify + swap)
    ├── backend_proc.rs     # locate + spawn + supervise yoink-core (sibling binary)
    ├── deeplink.rs         # yoink:// parsing + the per-user single-instance socket
    ├── minter.rs           # supervise the yoink-minter child (PO tokens; auto mode)
    ├── tray.rs             # system tray (show / quit)
    ├── theme.rs            # the design system: a typed Palette (dark + light) mapped
    │                       #   onto egui::Visuals — no CSS
    ├── fonts.rs            # register the bundled typefaces
    ├── icons.rs            # inline SVG icons (lucide) + site brand logos
    └── i18n.rs             # tl(lang, key): 14 UI languages, flat match table
```

## Conventions

- **State lives in the `App` struct** (`app.rs`); `fn ui(&mut self, …)` renders it
  each frame. The backend is reached only through the `Cmd`/`Evt` channels in
  `api.rs` — the UI thread never blocks on the network.
- **Design system:** colors are semantic tokens in `theme.rs` (`Palette`), defined
  for both dark and light and applied onto `egui::Visuals`. Components read the
  ambient style; there are no literal colors in the screens.
- **Fonts:** Gloock for display headings (`fonts::display()`), Inter for the UI,
  Inter SemiBold for emphasis (`fonts::semibold()`), all bundled.
- **i18n:** every user-facing string goes through `tl(lang, "key")`. The language
  is auto-detected from the OS locale and overridable in Settings (with a System
  option that follows the OS); the theme has the same System option, resolved via
  the XDG desktop portal off the UI thread. Both choices persist in
  `<config>/yoink/ui.json`.
- **Custom window chrome:** the app draws its own title bar (AMOLED, window
  buttons) and rounded corners (a transparent framebuffer + a painted rounded
  background + foreground resize strips) — see the title-bar / `resize_handles`
  code in `app.rs`.

## Headless screenshots

The app can render a screen to a PNG and exit via env vars, for reviewing the UI
without a display: `YOINK_SHOT=<path>` plus `YOINK_SHOT_TAB`,
`YOINK_SHOT_QUEUE`, `YOINK_SHOT_SCROLL`, `YOINK_SHOT_LIGHT`, `YOINK_FAKE_UPDATE`,
etc. On a Wayland host, run it under a headless X server with Wayland disabled so
it doesn't pop a real window:

```bash
env -u WAYLAND_DISPLAY GDK_BACKEND=x11 WINIT_UNIX_BACKEND=x11 \
  YOINK_SHOT=/tmp/shot.png YOINK_SHOT_TAB=ajustes YOINK_MINTER=/bin/true \
  xvfb-run -a -s "-screen 0 1400x900x24" ./target/release/yoink-desktop
```
