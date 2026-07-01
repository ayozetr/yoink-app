// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::Manager;

/// Holds the backend process handle so we can kill it when the app exits.
struct BackendProcess(Mutex<Option<Child>>);

/// The port the backend actually bound, exposed to the frontend so it can target
/// the right URL when 8756 was taken and we fell back to a free port.
struct BackendPort(u16);

/// The canonical port the bundled frontend expects by default.
const DEFAULT_PORT: u16 = 8756;

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
            if let Some(window) = app.webview_windows().values().next() {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .invoke_handler(tauri::generate_handler![is_appimage, backend_port])
        .setup(|app| {
            let port = pick_backend_port();
            let child = spawn_backend(app, port);
            // When the sidecar isn't bundled (dev mode), the backend runs
            // separately on the default port — advertise that, not the unused
            // port we just probed.
            let advertised = if child.is_some() { port } else { DEFAULT_PORT };
            app.manage(BackendProcess(Mutex::new(child)));
            app.manage(BackendPort(advertised));
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
