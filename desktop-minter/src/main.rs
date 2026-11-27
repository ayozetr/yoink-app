// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! `yoink-minter` — a headless (hidden-window) WebView whose only job is to mint
//! YouTube PO tokens for the native egui UI.
//!
//! The egui app has no JavaScript runtime, but YouTube's BotGuard (which issues
//! the token) is JS that must run in a browser engine. So the UI spawns this tiny
//! process when `po_token_mode == "auto"`: it opens an invisible `wry` WebView
//! running the bundled `bgutils-js` minter loop (see `web/main.js`), which
//! long-polls the local backend's `/api/po-token/*` endpoints and tunnels
//! BotGuard's network through the backend proxy — so this process only ever talks
//! to `127.0.0.1`. The UI kills it when auto mode turns off or the app exits.

use tao::event::Event;
use tao::event_loop::{ControlFlow, EventLoop};
use tao::window::WindowBuilder;
use wry::WebViewBuilder;

/// The minter loop + bgutils-js, bundled to one self-contained IIFE by Vite
/// (`web/vite.config.mjs`; regenerate after editing `web/main.js`).
const MINTER_JS: &str = include_str!("../web/dist/minter.js");

fn main() {
    let port: u16 = std::env::var("YOINK_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(8756);

    // Load a blank page *served by the backend* so this WebView shares the
    // backend's origin — its /api/po-token/* fetches are then same-origin (a
    // `with_html` page has a null origin the backend's CORS rejects). The bundled
    // bgutils minter loop is injected as an initialization script (it runs in that
    // origin, before any page script); the page itself has no CSP, so BotGuard's
    // `new Function` runs freely and the only network is the proxied fetch.
    let url = format!("http://127.0.0.1:{port}/api/po-token/host");
    let init = format!("window.YOINK_PORT={port};\n{MINTER_JS}");

    let event_loop = EventLoop::new();
    let window = WindowBuilder::new()
        .with_title("yoink-minter")
        .with_visible(false)
        .build(&event_loop)
        .expect("create hidden window");

    // On Linux, wry is backed by webkit2gtk and needs the window's GTK container
    // (a raw window handle is unavailable for a never-shown window); on other
    // platforms it builds straight from the window.
    #[cfg(target_os = "linux")]
    let _webview = {
        use tao::platform::unix::WindowExtUnix;
        use wry::WebViewBuilderExtUnix;
        let vbox = window.default_vbox().expect("gtk container");
        WebViewBuilder::new()
            .with_url(&url)
            .with_initialization_script(&init)
            .build_gtk(vbox)
            .expect("create webview")
    };
    #[cfg(not(target_os = "linux"))]
    let _webview = WebViewBuilder::new()
        .with_url(&url)
        .with_initialization_script(&init)
        .build(&window)
        .expect("create webview");

    event_loop.run(move |event, _target, control_flow| {
        *control_flow = ControlFlow::Wait;
        if let Event::LoopDestroyed = event {
            // nothing to clean up — the parent kills us
        }
    });
}
