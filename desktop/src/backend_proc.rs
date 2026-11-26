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
            // Release builds run ONLY the sibling (or $YOINK_CORE) — never a binary
            // found by walking ancestor dirs or on PATH, which another user could
            // plant. The ancestor walk / PATH fallback is a dev-only convenience.
            #[cfg(not(debug_assertions))]
            return sibling;
            // Dev convenience: a `cargo build` of the desktop crate doesn't ship
            // yoink-core beside it — find the workspace's backend build by walking
            // up to `backend-rs/target/{release,debug}`.
            #[cfg(debug_assertions)]
            for anc in dir.ancestors() {
                for sub in [
                    "backend-rs/target/release/yoink-core",
                    "backend-rs/target/debug/yoink-core",
                ] {
                    let cand = anc.join(sub);
                    if cand.exists() {
                        return cand;
                    }
                }
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
        // On Windows yoink-core is a console binary; without this it would pop a
        // console window behind the app. CREATE_NO_WINDOW keeps it hidden (and the
        // yt-dlp/ffmpeg children it spawns inherit no console either).
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        }
        // Hold the backend's stdin open: its watchdog exits the moment this pipe
        // closes, so the backend dies with us even on a hard kill (when Drop can't
        // run) — the same trick the Tauri shell used.
        cmd.env("YOINK_STDIN_WATCHDOG", "1").stdin(Stdio::piped());
        // Point it at the bundled yt-dlp/ffmpeg if they sit beside the binary
        // (`.exe` on Windows), so it never depends on PATH or the search order.
        if let Some(dir) = bin.parent().filter(|d| !d.as_os_str().is_empty()) {
            let exe = std::env::consts::EXE_SUFFIX; // "" on unix, ".exe" on Windows
            // Windows ships yt-dlp as a onedir build under ytdlp/ (yt-dlp.exe +
            // _internal/, so it doesn't self-extract on every run); other targets
            // keep the single binary beside us. Prefer the onedir when present.
            let onedir = dir.join("ytdlp").join(format!("yt-dlp{exe}"));
            let ytdlp = if onedir.exists() {
                onedir
            } else {
                dir.join(format!("yt-dlp{exe}"))
            };
            if ytdlp.exists() {
                cmd.env("YOINK_YTDLP", ytdlp);
            }
            if dir.join(format!("ffmpeg{exe}")).exists() {
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
