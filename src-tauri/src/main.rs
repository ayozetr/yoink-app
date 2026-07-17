// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager, WindowEvent};
use tauri_plugin_deep_link::DeepLinkExt;

/// Holds the backend process handle so we can kill it when the app exits.
struct BackendProcess(Mutex<Option<Child>>);

/// The port the backend actually bound, exposed to the frontend so it can target
/// the right URL when 8756 was taken and we fell back to a free port.
struct BackendPort(u16);

/// The canonical port the bundled frontend expects by default.
const DEFAULT_PORT: u16 = 8756;

/// Whether closing the window hides it to the tray instead of quitting. Mirrors the
/// `minimize_to_tray` setting; the frontend syncs it via `set_minimize_to_tray`.
struct MinimizeToTray(AtomicBool);

/// A `yoink://` URL the app was cold-started with, captured before the webview
/// exists. The frontend drains it once on mount via `take_pending_deep_link`; a
/// deep link that arrives while the app is already running is pushed live instead
/// (the `deep-link` event).
struct PendingDeepLink(Mutex<Option<String>>);

/// Opt-in global shortcuts (all Ctrl/Cmd+Shift+…), registered/unregistered together
/// from the frontend via `set_global_hotkey`.
const HK_ANALYZE: &str = "CmdOrCtrl+Shift+Y"; // bring to front + paste-and-analyze
const HK_TOGGLE: &str = "CmdOrCtrl+Shift+O"; // show/hide the window
const HK_QUICK: &str = "CmdOrCtrl+Shift+D"; // quick-download the clipboard (no window)
const HK_PASTE: &str = "CmdOrCtrl+Shift+P"; // bring to front + paste (no analyze)
const HK_CANCEL: &str = "CmdOrCtrl+Shift+X"; // cancel the current download
const HK_FOLDER: &str = "CmdOrCtrl+Shift+F"; // open the downloads folder

/// Pull the target media URL out of an incoming `yoink://` deep link.
///
/// Contract: `yoink://download?url=<percent-encoded target>` (the `download` host
/// is cosmetic; only the `url` query param is read). `query_pairs()` percent-
/// decodes it for us. Any link without a non-empty `url` param yields `None` and
/// is ignored, so a stray or malformed deep link can't drive a bogus analyze.
fn deep_link_target(link: &url::Url) -> Option<String> {
    for (key, value) in link.query_pairs() {
        if &*key == "url" {
            let target = value.trim();
            if !target.is_empty() {
                return Some(target.to_string());
            }
        }
    }
    None
}

/// Reveal + focus the main window — it may be hidden by close-to-tray, or minimized.
fn show_and_focus(app: &tauri::AppHandle) {
    if let Some(window) = app.webview_windows().values().next() {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// Show/hide the main window: hide it if it's visible + focused, otherwise reveal it.
fn toggle_window(app: &tauri::AppHandle) {
    if let Some(window) = app.webview_windows().values().next() {
        if window.is_visible().unwrap_or(true) && window.is_focused().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.unminimize();
            let _ = window.set_focus();
        }
    }
}

/// Pick a port for the backend: the canonical 8756 when it's free, otherwise an
/// OS-assigned free port.
///
/// A second Yoink instance can't reach here (the single-instance plugin focuses
/// the existing window first), so a busy 8756 means an *unrelated* program holds
/// it — falling back lets Yoink still start instead of failing to bind.
fn pick_backend_port() -> u16 {
    use std::net::TcpListener;
    // Probing by binding then dropping leaves a tiny race before uvicorn binds,
    // but the common path (8756 free) is unaffected and the fallback is rare.
    if TcpListener::bind(("127.0.0.1", DEFAULT_PORT)).is_ok() {
        return DEFAULT_PORT;
    }
    if let Ok(listener) = TcpListener::bind(("127.0.0.1", 0)) {
        if let Ok(addr) = listener.local_addr() {
            return addr.port();
        }
    }
    // Both the canonical port and an OS-assigned one failed to bind — something
    // is badly wrong with the loopback stack. Fall back to the default and warn,
    // so the inevitable bind failure downstream isn't a silent mystery.
    eprintln!("[yoink] could not bind any backend port; falling back to {DEFAULT_PORT}");
    DEFAULT_PORT
}

/// Locate the bundled backend executable inside the app's resource directory.
///
/// The backend ships as a PyInstaller **one-folder** distribution bundled as a
/// Tauri resource, so the exe lives next to its `_internal/` libraries. Try the
/// few layouts Tauri may place resources under, so a layout quirk on one platform
/// doesn't stop it being found. Returns `None` in dev (no bundled resource) — the
/// backend then runs separately on the default port.
fn backend_exe(app: &tauri::App) -> Option<PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    let name = if cfg!(windows) {
        "yoink-backend.exe"
    } else {
        "yoink-backend"
    };
    for sub in [
        "backend",
        "backend/yoink-backend",
        "binaries/yoink-backend",
        "resources/backend",
        "resources/binaries/yoink-backend",
    ] {
        let candidate = resource_dir.join(sub).join(name);
        if candidate.exists() {
            return Some(candidate);
        }
    }
    None
}

/// Spawn the bundled FastAPI backend, telling it which port to bind via
/// `YOINK_PORT`. Returns the child handle so the caller can terminate it on exit
/// (otherwise it would linger and hold the port). Its own logs still go to
/// `~/.yoink/logs/yoink.log`; stderr is inherited so a terminal launch shows it.
fn spawn_backend(app: &tauri::App, port: u16) -> Option<Child> {
    let exe = match backend_exe(app) {
        Some(path) => path,
        None => {
            eprintln!("[yoink] bundled backend not found (dev mode?) — skipping spawn");
            return None;
        }
    };

    // Resources can lose their executable bit when copied into the bundle; make
    // sure the exe is runnable before spawning it.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(meta) = std::fs::metadata(&exe) {
            let mut perms = meta.permissions();
            perms.set_mode(perms.mode() | 0o755);
            let _ = std::fs::set_permissions(&exe, perms);
        }
    }

    let mut command = Command::new(&exe);
    command
        .env("YOINK_PORT", port.to_string())
        // Give it a stdin pipe kept open for the process's lifetime (the Child
        // owns the write end). The backend's watchdog reads stdin and exits on
        // EOF, so if the app dies without running the exit handler, the closed
        // pipe still shuts the backend down instead of leaving it on the port.
        // (Inheriting stdin would EOF immediately with no tty — file-manager
        // launch — and wrongly trip that watchdog at startup.)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    // The backend is a console-subsystem exe; without this flag Windows opens a
    // visible terminal window for it. CREATE_NO_WINDOW hides it (the sidecar
    // plugin did this for us before) while the stdin pipe still works.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    match command.spawn() {
        Ok(child) => Some(child),
        Err(err) => {
            eprintln!("[yoink] failed to start backend: {err}");
            None
        }
    }
}

/// Terminate the backend and any children (e.g. a running ffmpeg) on app exit.
///
/// With the one-folder build the spawned exe *is* the backend process (no
/// PyInstaller bootloader indirection), so `kill()` ends it directly. Its
/// grandchildren are reaped first — by process group on Windows (`taskkill /T`)
/// and by parent PID on Unix — so nothing lingers holding the backend port.
fn kill_backend(mut child: Child) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let _ = Command::new("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    #[cfg(not(windows))]
    {
        let _ = Command::new("pkill")
            .args(["-TERM", "-P", &child.id().to_string()])
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}

/// Whether the app is running as a Linux AppImage — the only Linux package the
/// updater can replace in place. The frontend uses this to choose between an
/// in-app "download & install" and a "view release" link (for .deb/.rpm).
#[tauri::command]
fn is_appimage() -> bool {
    std::env::var_os("APPIMAGE").is_some()
}

/// The port the local backend is listening on (8756, or a fallback when taken).
#[tauri::command]
fn backend_port(state: tauri::State<'_, BackendPort>) -> u16 {
    state.0
}

/// Hand the frontend any `yoink://` URL the app was cold-started with, clearing it
/// so it's consumed once. Returns `None` on a normal launch. (A deep link while the
/// app is already running arrives via the `deep-link` event, not here.)
#[tauri::command]
fn take_pending_deep_link(state: tauri::State<'_, PendingDeepLink>) -> Option<String> {
    state.0.lock().ok().and_then(|mut guard| guard.take())
}

/// Sync the close-to-tray behaviour from the frontend (persisted in AppSettings).
#[tauri::command]
fn set_minimize_to_tray(state: tauri::State<'_, MinimizeToTray>, enabled: bool) {
    state.0.store(enabled, Ordering::Relaxed);
}

/// Enable/disable launching Yoink at system startup (tauri-plugin-autostart).
#[tauri::command]
fn set_autostart(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    use tauri_plugin_autostart::ManagerExt;
    let manager = app.autolaunch();
    let result = if enabled { manager.enable() } else { manager.disable() };
    result.map_err(|e| e.to_string())
}

/// Whether Yoink is currently registered to launch at startup.
#[tauri::command]
fn is_autostart_enabled(app: tauri::AppHandle) -> bool {
    use tauri_plugin_autostart::ManagerExt;
    app.autolaunch().is_enabled().unwrap_or(false)
}

/// Register/unregister the opt-in global shortcuts (all four together).
#[tauri::command]
fn set_global_hotkey(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
    let gs = app.global_shortcut();
    if !enabled {
        for hk in [HK_ANALYZE, HK_TOGGLE, HK_QUICK, HK_PASTE, HK_CANCEL, HK_FOLDER] {
            let _ = gs.unregister(hk);
        }
        return Ok(());
    }
    gs.on_shortcut(HK_ANALYZE, |app, _s, e| {
        if e.state() == ShortcutState::Pressed {
            show_and_focus(app);
            let _ = app.emit("global-hotkey", ()); // paste + analyze
        }
    })
    .map_err(|e| e.to_string())?;
    gs.on_shortcut(HK_TOGGLE, |app, _s, e| {
        if e.state() == ShortcutState::Pressed {
            toggle_window(app);
        }
    })
    .map_err(|e| e.to_string())?;
    gs.on_shortcut(HK_QUICK, |app, _s, e| {
        if e.state() == ShortcutState::Pressed {
            let _ = app.emit("global-quick-download", ()); // download without showing
        }
    })
    .map_err(|e| e.to_string())?;
    gs.on_shortcut(HK_PASTE, |app, _s, e| {
        if e.state() == ShortcutState::Pressed {
            show_and_focus(app);
            let _ = app.emit("global-paste", ()); // paste, no analyze
        }
    })
    .map_err(|e| e.to_string())?;
    gs.on_shortcut(HK_CANCEL, |app, _s, e| {
        if e.state() == ShortcutState::Pressed {
            let _ = app.emit("global-cancel", ()); // cancel the current download
        }
    })
    .map_err(|e| e.to_string())?;
    gs.on_shortcut(HK_FOLDER, |app, _s, e| {
        if e.state() == ShortcutState::Pressed {
            let _ = app.emit("global-open-folder", ()); // open the downloads folder
        }
    })
    .map_err(|e| e.to_string())?;
    Ok(())
}

fn main() {
    // WebKitGTK's DMABUF renderer leaves a blank window (or crashes with
    // "Gdk-Message: Error 71") on many Wayland sessions. Force the GL backend
    // before any Tauri / webview code touches the library, so the app boots
    // whether launched from a file manager or a terminal. Respect a value the
    // user has already set.
    #[cfg(target_os = "linux")]
    {
        if std::env::var_os("WEBKIT_DISABLE_DMABUF_RENDERER").is_none() {
            // SAFETY: single-threaded process at this point.
            unsafe {
                std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
            }
        }
    }

    tauri::Builder::default()
        // single-instance MUST be the first plugin. A second launch (or a launch
        // while an orphaned instance is still up) focuses the existing window
        // instead of starting a second sidecar that can't bind port 8756.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // Reveal the existing window (it may be hidden in the tray, not just
            // minimized) instead of starting a second instance. A yoink:// URL in
            // `_args` is forwarded to the deep-link handler by the plugin's
            // `deep-link` feature, so we don't parse it here.
            show_and_focus(app);
        }))
        // Must come after single-instance so a second launch's yoink:// URL reaches
        // this (already-running) instance's `on_open_url` handler.
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .invoke_handler(tauri::generate_handler![
            is_appimage,
            backend_port,
            set_minimize_to_tray,
            set_autostart,
            is_autostart_enabled,
            set_global_hotkey,
            take_pending_deep_link
        ])
        .on_window_event(|window, event| {
            // Close-to-tray: when enabled, closing the window hides it instead of
            // quitting. A real quit comes from the tray "Quit" item (app.exit(0)).
            if let WindowEvent::CloseRequested { api, .. } = event {
                let minimize = window
                    .app_handle()
                    .state::<MinimizeToTray>()
                    .0
                    .load(Ordering::Relaxed);
                if minimize {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .setup(|app| {
            let port = pick_backend_port();
            let child = spawn_backend(app, port);
            // When the sidecar isn't bundled (dev mode), the backend runs
            // separately on the default port — advertise that, not the unused
            // port we just probed.
            let advertised = if child.is_some() { port } else { DEFAULT_PORT };
            app.manage(BackendProcess(Mutex::new(child)));
            app.manage(BackendPort(advertised));
            // Close-to-tray defaults off; the frontend syncs the real setting on load.
            app.manage(MinimizeToTray(AtomicBool::new(false)));

            // Deep link (yoink://download?url=…). Register the scheme at runtime —
            // needed on Linux/Windows in dev, and on Linux it (re)writes the running
            // binary's user-level x-scheme-handler so an AppImage is reachable too;
            // the installer covers the packaged case. Idempotent, so it's harmless.
            #[cfg(any(windows, target_os = "linux"))]
            let _ = app.deep_link().register_all();

            // Cold start: the launching yoink:// URL arrives via argv before the
            // webview exists, so stash it for the frontend to drain once on mount.
            app.manage(PendingDeepLink(Mutex::new(
                app.deep_link()
                    .get_current()
                    .ok()
                    .flatten()
                    .and_then(|urls| urls.iter().find_map(deep_link_target)),
            )));

            // Already-running: single-instance forwards a second launch's URL here.
            // Reveal the window and push the target to the frontend to analyze.
            let dl_handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                for url in event.urls() {
                    if let Some(target) = deep_link_target(&url) {
                        show_and_focus(&dl_handle);
                        let _ = dl_handle.emit("deep-link", target);
                    }
                }
            });

            // Always-on system tray. Left-click or "Open Yoink" reveals the window;
            // "Quit" exits (triggering the backend cleanup in .run below).
            let open = MenuItem::with_id(app, "open", "Open Yoink", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().cloned().expect("bundled window icon"))
                .tooltip("Yoink")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_and_focus(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_and_focus(tray.app_handle());
                    }
                })
                .build(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the Yoink application")
        .run(|app_handle, event| {
            // Kill the backend sidecar when the app exits so it doesn't linger
            // holding the port.
            if matches!(
                event,
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
            ) {
                if let Some(state) = app_handle.try_state::<BackendProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(child) = guard.take() {
                            kill_backend(child);
                        }
                    }
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::deep_link_target;
    use url::Url;

    fn target(link: &str) -> Option<String> {
        deep_link_target(&Url::parse(link).expect("valid test URL"))
    }

    #[test]
    fn extracts_percent_decoded_url_param() {
        assert_eq!(
            target("yoink://download?url=https%3A%2F%2Fx.com%2Fa%2Fstatus%2F1"),
            Some("https://x.com/a/status/1".to_string())
        );
    }

    #[test]
    fn ignores_links_without_a_usable_url_param() {
        assert_eq!(target("yoink://download"), None);
        assert_eq!(target("yoink://download?foo=bar"), None);
        assert_eq!(target("yoink://download?url="), None); // empty -> ignored
        assert_eq!(target("yoink://download?url=%20%20"), None); // whitespace only
    }

    #[test]
    fn trims_surrounding_whitespace() {
        assert_eq!(
            target("yoink://download?url=%20https%3A%2F%2Fy.com%20"),
            Some("https://y.com".to_string())
        );
    }
}
