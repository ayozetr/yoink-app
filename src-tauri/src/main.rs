// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

/// Spawn the bundled FastAPI backend (PyInstaller sidecar) and pipe its logs.
///
/// In development the backend is started by `beforeDevCommand` instead, so a
/// missing sidecar is not an error — we just skip it.
fn spawn_backend(app: &tauri::App) {
    let sidecar = match app.shell().sidecar("yoink-backend") {
        Ok(command) => command,
        Err(err) => {
            eprintln!("[yoink] backend sidecar unavailable (dev mode?): {err}");
            return;
        }
    };

    match sidecar.spawn() {
        Ok((mut rx, _child)) => {
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
        }
        Err(err) => eprintln!("[yoink] failed to start backend: {err}"),
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
            spawn_backend(app);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the Yoink application");
}
