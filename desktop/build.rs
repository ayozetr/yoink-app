// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Embed the application icon into the Windows `.exe` so Explorer, the taskbar
//! and shortcuts show it. (The in-window icon is drawn by the app itself; this
//! is the executable's file icon, which needs a Win32 resource.) A no-op when
//! the build target isn't Windows.

fn main() {
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        println!("cargo:rerun-if-changed=assets/icon.ico");
        let mut res = winresource::WindowsResource::new();
        res.set_icon("assets/icon.ico");
        if let Err(e) = res.compile() {
            println!("cargo:warning=failed to embed the Windows icon: {e}");
        }
    }
}
