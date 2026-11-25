// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! `yoink://` deep links + single-instance. The browser and the "Send to Yoink"
//! extension launch `yoink://download?url=<encoded>`; this hands that URL to the
//! already-running app (over a Unix socket) instead of opening a second window,
//! and surfaces incoming links to the UI through a channel.

#[cfg(unix)]
use std::io::{Read, Write};
#[cfg(unix)]
use std::os::unix::net::{UnixListener, UnixStream};
use std::sync::mpsc::Sender;

#[cfg(unix)]
fn sock_path() -> std::path::PathBuf {
    if let Ok(p) = std::env::var("YOINK_DESKTOP_SOCK") {
        if !p.is_empty() {
            return p.into();
        }
    }
    // Prefer the per-user runtime dir (mode 0700). If it's unset, fall back to a
    // per-uid directory we create 0700 under the system temp dir — never a shared,
    // world-writable path like plain /tmp, so no other local user can reach it.
    if let Ok(dir) = std::env::var("XDG_RUNTIME_DIR") {
        if !dir.is_empty() {
            return std::path::PathBuf::from(dir).join("yoink-desktop.sock");
        }
    }
    use std::os::unix::fs::PermissionsExt;
    let uid = unsafe { libc::getuid() };
    let dir = std::env::temp_dir().join(format!("yoink-{uid}"));
    let _ = std::fs::create_dir_all(&dir);
    let _ = std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700));
    dir.join("yoink-desktop.sock")
}

/// Percent-decode (and `+` → space), enough for a URL carried in a deep link.
fn pct_decode(s: &str) -> String {
    let b = s.as_bytes();
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        match b[i] {
            b'%' if i + 2 < b.len() => {
                let hex = std::str::from_utf8(&b[i + 1..i + 3]).unwrap_or("");
                if let Ok(byte) = u8::from_str_radix(hex, 16) {
                    out.push(byte);
                    i += 3;
                    continue;
                }
                out.push(b'%');
            }
            b'+' => out.push(b' '),
            c => out.push(c),
        }
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// Extract the target URL from a `yoink://download?url=<enc>` (or bare
/// `yoink://<enc>`) link.
pub fn parse(link: &str) -> Option<String> {
    let rest = link.strip_prefix("yoink://")?;
    let raw = match rest.split_once("url=") {
        Some((_, after)) => after.split('&').next().unwrap_or(""),
        None => rest
            .trim_start_matches("download")
            .trim_start_matches(['?', '/']),
    };
    let decoded = pct_decode(raw);
    decoded.starts_with("http").then_some(decoded)
}

/// The deep-link URL this process was launched with, if any.
pub fn url_from_args() -> Option<String> {
    std::env::args().skip(1).find_map(|a| parse(&a))
}

/// Claim the single-instance slot. If another instance is already running, hand
/// it `pending` and return `true` (the caller should exit). Otherwise take over,
/// start a listener that forwards future links to `tx`, and return `false`.
#[cfg(unix)]
pub fn single_instance(pending: Option<String>, tx: Sender<String>) -> bool {
    let path = sock_path();
    if let Ok(mut stream) = UnixStream::connect(&path) {
        if let Some(url) = pending {
            let _ = stream.write_all(url.as_bytes());
        }
        return true; // a live instance took it
    }
    let _ = std::fs::remove_file(&path); // clear a stale socket (the dir is ours, 0700)
    if let Ok(listener) = UnixListener::bind(&path) {
        // Only the owner may talk to the socket.
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600));
        std::thread::spawn(move || {
            for stream in listener.incoming().flatten() {
                let mut buf = String::new();
                let s = stream;
                // A deep-link URL is tiny; cap the read so a local peer can't stream
                // unbounded data into memory / hang this thread.
                if s.take(8192).read_to_string(&mut buf).is_ok() {
                    if let Some(url) = parse(buf.trim()).or_else(|| {
                        buf.trim()
                            .starts_with("http")
                            .then(|| buf.trim().to_string())
                    }) {
                        let _ = tx.send(url);
                    }
                }
            }
        });
    }
    false
}

/// Windows single-instance + deep-link handoff over a per-user named pipe
/// (`\\.\pipe\yoink-desktop-<user>`), the counterpart of the Unix socket above.
#[cfg(windows)]
pub fn single_instance(pending: Option<String>, tx: Sender<String>) -> bool {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Foundation::{CloseHandle, GetLastError, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{CreateFileW, ReadFile, WriteFile, OPEN_EXISTING};
    use windows_sys::Win32::System::Pipes::{
        ConnectNamedPipe, CreateNamedPipeW, DisconnectNamedPipe,
    };

    const GENERIC_WRITE: u32 = 0x4000_0000;
    const PIPE_ACCESS_INBOUND: u32 = 0x0000_0001;
    const PIPE_UNLIMITED_INSTANCES: u32 = 255;
    const ERROR_PIPE_CONNECTED: u32 = 535;

    let user = std::env::var("USERNAME").unwrap_or_default();
    let name = format!(r"\\.\pipe\yoink-desktop-{user}");
    let wname: Vec<u16> = std::ffi::OsStr::new(&name)
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();

    // Client path: if a server is already listening, hand off the URL and exit.
    unsafe {
        let h = CreateFileW(
            wname.as_ptr(),
            GENERIC_WRITE,
            0,
            std::ptr::null(),
            OPEN_EXISTING,
            0,
            std::ptr::null_mut(),
        );
        if h != INVALID_HANDLE_VALUE {
            if let Some(url) = pending {
                let bytes = url.as_bytes();
                let mut written = 0u32;
                let _ = WriteFile(
                    h,
                    bytes.as_ptr(),
                    bytes.len() as u32,
                    &mut written,
                    std::ptr::null_mut(),
                );
            }
            CloseHandle(h);
            return true; // a live instance took it
        }
    }

    // Owner path: serve the pipe on a background thread, forwarding links to `tx`.
    std::thread::spawn(move || unsafe {
        loop {
            let pipe = CreateNamedPipeW(
                wname.as_ptr(),
                PIPE_ACCESS_INBOUND,
                0, // PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT are all 0
                PIPE_UNLIMITED_INSTANCES,
                0,
                8192,
                0,
                std::ptr::null(),
            );
            if pipe == INVALID_HANDLE_VALUE {
                break;
            }
            // A client connecting between CreateNamedPipe and ConnectNamedPipe
            // surfaces as ERROR_PIPE_CONNECTED, which is also success.
            let connected = ConnectNamedPipe(pipe, std::ptr::null_mut()) != 0
                || GetLastError() == ERROR_PIPE_CONNECTED;
            if connected {
                let mut buf = [0u8; 8192];
                let mut read = 0u32;
                if ReadFile(
                    pipe,
                    buf.as_mut_ptr(),
                    buf.len() as u32,
                    &mut read,
                    std::ptr::null_mut(),
                ) != 0
                    && read > 0
                {
                    let s = String::from_utf8_lossy(&buf[..read as usize]).to_string();
                    let url = parse(s.trim())
                        .or_else(|| s.trim().starts_with("http").then(|| s.trim().to_string()));
                    if let Some(url) = url {
                        let _ = tx.send(url);
                    }
                }
            }
            DisconnectNamedPipe(pipe);
            CloseHandle(pipe);
        }
    });
    false
}

#[cfg(not(any(unix, windows)))]
pub fn single_instance(_pending: Option<String>, _tx: Sender<String>) -> bool {
    false
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    #[test]
    fn parse_pulls_the_url() {
        assert_eq!(
            parse("yoink://download?url=https%3A%2F%2Fa.com%2Fx%3Fv%3D1").as_deref(),
            Some("https://a.com/x?v=1")
        );
        assert_eq!(
            parse("yoink://https%3A%2F%2Fb.com").as_deref(),
            Some("https://b.com")
        );
        assert_eq!(parse("http://not-a-deeplink"), None);
        assert_eq!(parse("yoink://download?url=ftp%3A%2F%2Fx"), None);
    }

    #[test]
    fn handoff_delivers_to_the_owner() {
        let sock = std::env::temp_dir().join(format!("yoink-test-{}.sock", std::process::id()));
        std::env::set_var("YOINK_DESKTOP_SOCK", &sock);
        let _ = std::fs::remove_file(&sock);

        // First claim owns the slot and listens.
        let (tx, rx) = std::sync::mpsc::channel();
        assert!(
            !single_instance(None, tx),
            "first instance should be the owner"
        );

        // Second claim hands its link over and signals the caller to exit.
        let (tx2, _rx2) = std::sync::mpsc::channel();
        assert!(
            single_instance(Some("https://x.test/v".into()), tx2),
            "second instance should hand off"
        );

        let got = rx
            .recv_timeout(std::time::Duration::from_secs(2))
            .expect("owner receives it");
        assert_eq!(got, "https://x.test/v");
        let _ = std::fs::remove_file(&sock);
        std::env::remove_var("YOINK_DESKTOP_SOCK");
    }
}
