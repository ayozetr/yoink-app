// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! System tray icon (Linux). The tray needs a GTK main loop, which can't share
//! eframe's winit loop, so it runs on its own thread; menu clicks come back to the
//! UI over a channel. A GTK-init failure (no tray in the session) is swallowed —
//! the app runs fine without a tray.

/// What the tray asks the UI to do.
// The tray is GTK-based (Linux only); on other platforms `spawn` is a no-op and
// these variants are never constructed.
#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
pub enum TrayMsg {
    Show,
    Quit,
}

#[cfg(target_os = "linux")]
pub fn spawn(tx: std::sync::mpsc::Sender<TrayMsg>, show_label: String, quit_label: String) {
    std::thread::spawn(move || {
        if gtk::init().is_err() {
            return;
        }
        use tray_icon::menu::{Menu, MenuEvent, MenuItem};
        use tray_icon::TrayIconBuilder;

        let menu = Menu::new();
        let show = MenuItem::new(&show_label, true, None);
        let quit = MenuItem::new(&quit_label, true, None);
        let _ = menu.append(&show);
        let _ = menu.append(&quit);

        let Ok(_tray) = TrayIconBuilder::new()
            .with_menu(Box::new(menu))
            .with_tooltip("Yoink")
            .with_icon(icon())
            .build()
        else {
            return;
        };

        let (show_id, quit_id) = (show.id().clone(), quit.id().clone());
        glib::timeout_add_local(std::time::Duration::from_millis(200), move || {
            while let Ok(ev) = MenuEvent::receiver().try_recv() {
                if ev.id == show_id {
                    let _ = tx.send(TrayMsg::Show);
                } else if ev.id == quit_id {
                    let _ = tx.send(TrayMsg::Quit);
                }
            }
            glib::ControlFlow::Continue
        });

        gtk::main();
    });
}

#[cfg(target_os = "linux")]
fn icon() -> tray_icon::Icon {
    let img = image::load_from_memory(include_bytes!("../assets/icon.png"))
        .map(|i| i.to_rgba8())
        .unwrap_or_default();
    let (w, h) = (img.width(), img.height());
    tray_icon::Icon::from_rgba(img.into_raw(), w, h)
        .unwrap_or_else(|_| tray_icon::Icon::from_rgba(vec![0, 0, 0, 0], 1, 1).unwrap())
}

#[cfg(not(target_os = "linux"))]
pub fn spawn(_tx: std::sync::mpsc::Sender<TrayMsg>, _show_label: String, _quit_label: String) {}
