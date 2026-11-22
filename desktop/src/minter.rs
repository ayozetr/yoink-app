// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Supervises the `yoink-minter` child process — the hidden WebView that mints
//! YouTube PO tokens (see the `yoink-minter` crate). It runs only while
//! `po_token_mode` is `"auto"`; this guard starts it on demand and kills it when
//! the mode turns off or the app exits.

use std::process::{Child, Command};

pub struct Minter {
    child: Option<Child>,
    port: u16,
}

impl Minter {
    pub fn new(port: u16) -> Minter {
        Minter { child: None, port }
    }

    /// Reconcile the child with whether auto-minting is wanted.
    pub fn set_auto(&mut self, want: bool) {
        match (want, self.child.is_some()) {
            (true, false) => self.child = spawn(self.port),
            (false, true) => self.kill(),
            _ => {}
        }
    }

    fn kill(&mut self) {
        if let Some(mut c) = self.child.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }

    /// Kill the child before a hard `process::exit` (which skips `Drop`), so the
    /// hidden WebView isn't orphaned.
    pub fn shutdown(&mut self) {
        self.kill();
    }
}

impl Drop for Minter {
    fn drop(&mut self) {
        self.kill();
    }
}

/// The `yoink-minter` binary: `YOINK_MINTER`, else a sibling of this executable,
/// else on `PATH`.
fn binary() -> std::path::PathBuf {
    if let Ok(p) = std::env::var("YOINK_MINTER") {
        if !p.is_empty() {
            return p.into();
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let sibling = dir.join("yoink-minter");
            // Release builds run only the sibling (or $YOINK_MINTER) — never a
            // binary found on PATH, which another user could plant. Dev builds
            // keep the PATH fallback below for convenience.
            #[cfg(not(debug_assertions))]
            return sibling;
            #[cfg(debug_assertions)]
            if sibling.exists() {
                return sibling;
            }
        }
    }
    "yoink-minter".into()
}

fn spawn(port: u16) -> Option<Child> {
    Command::new(binary())
        .env("YOINK_PORT", port.to_string())
        .spawn()
        .ok()
}
