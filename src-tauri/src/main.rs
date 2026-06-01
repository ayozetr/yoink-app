// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;

use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the backend sidecar handle so we can kill it when the app exits.
struct BackendProcess(Mutex<Option<CommandChild>>);

/// Spawn the bundled FastAPI backend (PyInstaller sidecar) and pipe its logs.
///
/// In development the backend is started separately, so a missing sidecar is
/// not an error — we just skip it. Returns the child handle so the caller can
/// terminate it on exit (otherwise it would linger and hold the port).
fn spawn_backend(app: &tauri::App) -> Option<CommandChild> {
    let sidecar = match app.shell().sidecar("yoink-backend") {
        Ok(command) => command,
        Err(err) => {
            eprintln!("[yoink] backend sidecar unavailable (dev mode?): {err}");
            return None;
        }
    };

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
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let child = spawn_backend(app);
            app.manage(BackendProcess(Mutex::new(child)));
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
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
