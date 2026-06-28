// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;

use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the backend sidecar handle so we can kill it when the app exits.
struct BackendProcess(Mutex<Option<CommandChild>>);

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

/// Spawn the bundled FastAPI backend (PyInstaller sidecar) and pipe its logs.
///
/// The sidecar is told which port to bind via `YOINK_PORT`. In development the
/// backend is started separately, so a missing sidecar is not an error — we just
/// skip it. Returns the child handle so the caller can terminate it on exit
/// (otherwise it would linger and hold the port).
fn spawn_backend(app: &tauri::App, port: u16) -> Option<CommandChild> {
    let sidecar = match app.shell().sidecar("yoink-backend") {
        Ok(command) => command,
        Err(err) => {
            eprintln!("[yoink] backend sidecar unavailable (dev mode?): {err}");
            return None;
        }
    };
    let sidecar = sidecar.env("YOINK_PORT", port.to_string());

    match sidecar.spawn() {
        Ok((mut rx, child)) => {
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                            eprint!("[backend] {}", String::from_utf8_lossy(&line));
                        }
                        _ => {}
                    }
                }
            });
            Some(child)
        }
        Err(err) => {
            eprintln!("[yoink] failed to start backend: {err}");
            None
        }
    }
}

/// Terminate the backend sidecar and its entire process tree.
///
/// PyInstaller's `--onefile` exe is a *bootloader* that spawns the real Python
/// process as a child. `CommandChild::kill()` only reaps the bootloader, so the
/// Python child must be taken down separately or it lingers holding the backend
/// port (on Windows it also keeps `yoink-backend.exe` open, breaking the NSIS
/// updater). Kill the whole tree by PID on Windows; on Unix kill the bootloader
/// and its child explicitly (closing stdin also trips the sidecar's in-process
/// watchdog as a backstop).
fn kill_sidecar(child: CommandChild) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let pid = child.pid();
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    #[cfg(not(windows))]
    {
        // Kill the bootloader's Python child directly (by parent PID) so it can't
        // linger on the backend port if the stdin-EOF watchdog is slow, then reap
        // the bootloader itself.
        let _ = std::process::Command::new("pkill")
            .args(["-TERM", "-P", &child.pid().to_string()])
            .status();
        let _ = child.kill();
    }
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
        .plugin(tauri_plugin_shell::init())
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
                            kill_sidecar(child);
                        }
                    }
                }
            }
        });
}
