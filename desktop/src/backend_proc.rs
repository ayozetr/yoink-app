// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Spawns and supervises the `yoink-core` backend, so the native app is
//! self-contained (the Tauri shell used to do this). If a backend is already
//! serving the port — a developer's `cargo run` — it's reused untouched.

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

fn responding() -> bool {
    TcpStream::connect(("127.0.0.1", crate::api::port())).is_ok()
}

/// The `yoink-core` binary: `YOINK_CORE`, else a sibling of this executable, else
/// on `PATH`.
fn locate() -> PathBuf {
    if let Ok(p) = std::env::var("YOINK_CORE") {
        if !p.is_empty() {
            return p.into();
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let sibling = dir.join("yoink-core");
            if sibling.exists() {
                return sibling;
            }
        }
    }
    "yoink-core".into()
}

/// Owns the spawned backend (if we started one) and stops it on drop.
pub struct Backend(Option<Child>);

impl Backend {
    /// Start the backend unless one is already serving the port, then wait (up to
    /// ~8 s) for it to accept connections.
    pub fn ensure() -> Backend {
        if responding() {
            return Backend(None); // reuse a dev backend
        }
        let bin = locate();
        let mut cmd = Command::new(&bin);
        // Hold the backend's stdin open: its watchdog exits the moment this pipe
        // closes, so the backend dies with us even on a hard kill (when Drop can't
        // run) — the same trick the Tauri shell used.
        cmd.env("YOINK_STDIN_WATCHDOG", "1").stdin(Stdio::piped());
        // Point it at the bundled yt-dlp/ffmpeg if they sit beside the binary.
        if let Some(dir) = bin.parent().filter(|d| !d.as_os_str().is_empty()) {
            let ytdlp = dir.join("yt-dlp");
            if ytdlp.exists() {
                cmd.env("YOINK_YTDLP", ytdlp);
            }
            if dir.join("ffmpeg").exists() {
                cmd.env("YOINK_FFMPEG", dir);
            }
        }
        // Keep the child (incl. its stdin) alive for the app's lifetime.
        let child = cmd.spawn().ok();
        if child.is_some() {
            let deadline = Instant::now() + Duration::from_secs(8);
            while Instant::now() < deadline && !responding() {
                std::thread::sleep(Duration::from_millis(100));
            }
        }
        Backend(child)
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        if let Some(mut c) = self.0.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }
}
