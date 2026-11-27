// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Optional Discord Rich Presence. The IPC calls block, so this runs on its own
//! thread driven by a channel: the UI sends state changes, the thread keeps the
//! connection and pushes the presence. It degrades silently when Discord isn't
//! running (and retries), and is a no-op while disabled. Cross-platform — the
//! crate speaks Discord's Unix socket on Linux/macOS and its named pipe on
//! Windows.

use discord_rich_presence::{activity, DiscordIpc, DiscordIpcClient};
use std::sync::mpsc::{channel, Receiver, RecvTimeoutError, Sender};
use std::time::{Duration, Instant};

/// The Discord application (set up at discord.com/developers). Its name is what
/// shows as "Playing <name>"; the strings below are the details/state/button.
const APP_ID: &str = "1575704228532461568";
const REPO_URL: &str = "https://github.com/ayozetr/yoink-app";
const BUTTON_LABEL: &str = "Download Yoink";

/// What the presence should show.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Presence {
    /// Window open, nothing downloading.
    Idle,
    /// Window open, a download in progress.
    Downloading,
    /// Window hidden in the tray — the presence is cleared.
    Hidden,
}

enum Msg {
    Set(Presence),
    Enabled(bool),
    Shutdown,
}

/// A handle to the presence thread. Dropping it shuts the thread down.
pub struct Discord {
    tx: Sender<Msg>,
}

impl Discord {
    /// Spawn the presence thread with the given initial enabled state.
    pub fn spawn(enabled: bool) -> Self {
        let (tx, rx) = channel();
        let _ = std::thread::Builder::new()
            .name("discord-rpc".into())
            .spawn(move || run(rx, enabled));
        Self { tx }
    }

    /// Set the presence (deduplicated by the thread; cheap to call often).
    pub fn set(&self, p: Presence) {
        let _ = self.tx.send(Msg::Set(p));
    }

    /// Turn the presence on/off (the toggle in Settings).
    pub fn set_enabled(&self, on: bool) {
        let _ = self.tx.send(Msg::Enabled(on));
    }
}

impl Drop for Discord {
    fn drop(&mut self) {
        let _ = self.tx.send(Msg::Shutdown);
    }
}

fn activity_for(p: Presence) -> activity::Activity<'static> {
    let details = match p {
        Presence::Downloading => "Downloading media…",
        // Hidden never reaches here (it clears instead); treat like Idle.
        Presence::Idle | Presence::Hidden => "Idle",
    };
    activity::Activity::new()
        // Shows as "Watching Yoink · <details>" rather than "Playing Yoink".
        .activity_type(activity::ActivityType::Watching)
        .details(details)
        .buttons(vec![activity::Button::new(BUTTON_LABEL, REPO_URL)])
}

fn run(rx: Receiver<Msg>, mut enabled: bool) {
    let mut client: Option<DiscordIpcClient> = None;
    let mut connected = false;
    let mut desired = Presence::Idle;
    let mut applied: Option<Presence> = None;
    // Force the first reconnect attempt immediately.
    let mut last_try = Instant::now()
        .checked_sub(Duration::from_secs(60))
        .unwrap_or_else(Instant::now);

    loop {
        // Block for messages, but wake every 2s so we can retry a dropped
        // connection even when the UI is quiet.
        match rx.recv_timeout(Duration::from_secs(2)) {
            Ok(Msg::Set(p)) => desired = p,
            Ok(Msg::Enabled(on)) => {
                enabled = on;
                if !on {
                    if let Some(c) = client.as_mut() {
                        let _ = c.clear_activity();
                        let _ = c.close();
                    }
                    client = None;
                    connected = false;
                    applied = None;
                }
            }
            Ok(Msg::Shutdown) => {
                if let Some(c) = client.as_mut() {
                    let _ = c.clear_activity();
                    let _ = c.close();
                }
                return;
            }
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => return,
        }

        if !enabled {
            continue;
        }

        // (Re)connect if needed, at most once every ~15s so a closed Discord
        // doesn't spin.
        if !connected && last_try.elapsed() >= Duration::from_secs(15) {
            last_try = Instant::now();
            let c = client.get_or_insert_with(|| DiscordIpcClient::new(APP_ID));
            if c.connect().is_ok() {
                connected = true;
                applied = None;
            } else {
                client = None;
            }
        }

        // Push the presence when it changed. Hidden clears it; the rest set it.
        if connected && applied != Some(desired) {
            if let Some(c) = client.as_mut() {
                let r = if desired == Presence::Hidden {
                    c.clear_activity()
                } else {
                    c.set_activity(activity_for(desired))
                };
                if r.is_ok() {
                    applied = Some(desired);
                } else {
                    // Discord went away — reset and let the retry path reconnect.
                    connected = false;
                    client = None;
                    applied = None;
                }
            }
        }
    }
}
