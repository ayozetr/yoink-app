// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

// On Windows, a release build is a GUI app: no console window behind it. Debug
// builds keep the console so `println!`/panics stay visible while developing.
#![cfg_attr(
    all(target_os = "windows", not(debug_assertions)),
    windows_subsystem = "windows"
)]

//! Yoink native desktop UI (egui). It renders straight to the GPU — no WebView,
//! no HTML/JS — and drives the local `yoink-core` backend over its REST/WS API.
//! A hidden WebView (`yoink-minter`) is spawned only for YouTube PO-token minting,
//! the one thing that still needs a JS runtime.

mod api;
mod app;
mod backend_proc;
mod deeplink;
mod fonts;
mod i18n;
mod icons;
mod minter;
mod theme;
mod tray;
mod win_chrome;

/// The window/taskbar icon, decoded from the bundled PNG.
fn icon() -> egui::IconData {
    match image::load_from_memory(include_bytes!("../assets/icon.png")) {
        Ok(img) => {
            let img = img.to_rgba8();
            let (width, height) = (img.width(), img.height());
            egui::IconData {
                rgba: img.into_raw(),
                width,
                height,
            }
        }
        Err(_) => egui::IconData::default(),
    }
}

/// On Wayland the window icon isn't taken from `with_icon`; the compositor maps
/// the window's `app_id` to a `.desktop` entry and uses its `Icon`. When running
/// an un-installed binary there's no such entry, so the title bar/dock shows a
/// generic icon. Drop a user-level desktop entry + icon (idempotent) so the real
/// Yoink icon shows up. A system install (install.sh) still provides its own.
#[cfg(target_os = "linux")]
fn ensure_desktop_entry() {
    let Some(home) = std::env::var_os("HOME").map(std::path::PathBuf::from) else {
        return;
    };
    let data = std::env::var_os("XDG_DATA_HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| home.join(".local/share"));
    let icon_dir = data.join("icons/hicolor/512x512/apps");
    let app_dir = data.join("applications");
    let _ = std::fs::create_dir_all(&icon_dir);
    let _ = std::fs::create_dir_all(&app_dir);

    let icon_path = icon_dir.join("yoink.png");
    if !icon_path.exists() {
        let _ = std::fs::write(&icon_path, include_bytes!("../assets/icon.png"));
    }
    let exec = std::env::current_exe()
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| "yoink-desktop".into());
    let entry = format!(
        "[Desktop Entry]\nType=Application\nName=Yoink\nComment=Download high-fidelity video and audio\nExec={exec} %u\nIcon=yoink\nTerminal=false\nCategories=AudioVideo;Network;\nStartupWMClass=yoink\nMimeType=x-scheme-handler/yoink;\n"
    );
    let dpath = app_dir.join("yoink.desktop");
    let up_to_date = std::fs::read_to_string(&dpath)
        .map(|c| c.contains(&format!("Exec={exec} ")))
        .unwrap_or(false);
    if !up_to_date {
        let _ = std::fs::write(&dpath, entry);
    }
}

fn main() -> eframe::Result {
    // Tie this process (taskbar grouping + toast notifications) to our own
    // AppUserModelID — the one the installer registers — so Windows shows
    // "Yoink" on notifications instead of the launching process.
    #[cfg(target_os = "windows")]
    unsafe {
        let aumid: Vec<u16> = "app.yoink.desktop\0".encode_utf16().collect();
        windows_sys::Win32::UI::Shell::SetCurrentProcessExplicitAppUserModelID(aumid.as_ptr());
    }

    #[cfg(target_os = "linux")]
    ensure_desktop_entry();

    // Clean up the previous binary left beside us by a Windows in-place update.
    #[cfg(target_os = "windows")]
    if let Ok(exe) = std::env::current_exe() {
        let _ = std::fs::remove_file(exe.with_extension("old"));
    }

    // Deep link + single instance: if a yoink:// link was passed and another
    // instance is already running, hand it over and exit; otherwise we become the
    // owner and receive future links on `dl_rx`.
    let pending = deeplink::url_from_args();
    let (dl_tx, dl_rx) = std::sync::mpsc::channel::<String>();
    if deeplink::single_instance(pending.clone(), dl_tx) {
        return Ok(());
    }

    // Start (and own) the backend if one isn't already running; dropped on exit.
    let _backend = backend_proc::Backend::ensure();

    // System tray (its clicks come back over this channel). Labels in the OS
    // language the app starts in.
    let (tray_tx, tray_rx) = std::sync::mpsc::channel::<tray::TrayMsg>();
    let tl = crate::i18n::detect();
    tray::spawn(
        tray_tx,
        crate::i18n::tl(tl, "tray.show").to_string(),
        crate::i18n::tl(tl, "tray.quit").to_string(),
    );

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Yoink")
            .with_app_id("yoink")
            // Draw our own title bar (a flat AMOLED strip with the Yoink mark),
            // so the window chrome matches the app instead of the compositor's
            // gray decoration — and looks identical across Linux/Windows/macOS.
            .with_decorations(false)
            // Transparent so we can round the window corners ourselves (the app
            // paints a rounded background; the corners outside it stay clear).
            // Not on Windows: its window surface is opaque (the "transparent"
            // corners would fill black), so there we keep the window opaque and
            // let DWM round the corners natively (see win_chrome::set_rounding).
            .with_transparent(cfg!(not(target_os = "windows")))
            .with_inner_size([1180.0, 840.0])
            .with_min_inner_size([560.0, 520.0])
            .with_icon(icon()),
        ..Default::default()
    };
    eframe::run_native(
        "Yoink",
        options,
        Box::new(move |cc| Ok(Box::new(app::App::new(cc, pending, dl_rx, tray_rx)))),
    )
}
