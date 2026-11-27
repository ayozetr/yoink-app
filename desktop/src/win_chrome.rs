// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Native window-corner rounding on Windows (DWM); a no-op elsewhere.
//!
//! The app is a borderless window (it draws its own title bar). On Wayland it
//! rounds its own corners via a transparent framebuffer, but Windows paints the
//! window surface opaque — those "transparent" corners would show as black — so
//! on Windows we keep the window opaque (see `main.rs`) and ask DWM to clip the
//! corners the native Windows 11 way instead.

/// Round (`true`) or square (`false`) the app window's corners.
#[cfg(target_os = "windows")]
pub fn set_rounding(round: bool) {
    use core::ffi::c_void;
    use windows_sys::Win32::Graphics::Dwm::DwmSetWindowAttribute;
    use windows_sys::Win32::UI::WindowsAndMessaging::FindWindowW;

    const DWMWA_WINDOW_CORNER_PREFERENCE: u32 = 33;
    const DWMWCP_DONOTROUND: i32 = 1;
    const DWMWCP_ROUND: i32 = 2;

    // The window is titled "Yoink" (ViewportBuilder::with_title); find it by name.
    let title: Vec<u16> = "Yoink".encode_utf16().chain(std::iter::once(0)).collect();
    let pref: i32 = if round {
        DWMWCP_ROUND
    } else {
        DWMWCP_DONOTROUND
    };
    unsafe {
        let hwnd = FindWindowW(std::ptr::null(), title.as_ptr());
        if !hwnd.is_null() {
            // Best-effort: a failure just leaves the corners as they were.
            let _ = DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                &pref as *const i32 as *const c_void,
                core::mem::size_of::<i32>() as u32,
            );
        }
    }
}

#[cfg(not(target_os = "windows"))]
pub fn set_rounding(_round: bool) {}
