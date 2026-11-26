// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Embed the application icon and version metadata into the Windows `.exe` so
//! Explorer (icon + the Details tab: product name, version, company,
//! copyright), the taskbar and shortcuts show them. (The in-window icon is
//! drawn by the app itself; this is the executable's file icon + VERSIONINFO
//! resource.) A no-op when the build target isn't Windows.

fn main() {
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        println!("cargo:rerun-if-changed=assets/icon.ico");

        // "4.4.0" -> the packed u64 Win32 FILEVERSION (major, minor, patch, 0).
        let ver = std::env::var("CARGO_PKG_VERSION").unwrap_or_default();
        let mut parts = ver.split('.').map(|s| s.parse::<u16>().unwrap_or(0));
        let (maj, min, pat) = (
            parts.next().unwrap_or(0),
            parts.next().unwrap_or(0),
            parts.next().unwrap_or(0),
        );
        let packed = ((maj as u64) << 48) | ((min as u64) << 32) | ((pat as u64) << 16);

        let mut res = winresource::WindowsResource::new();
        res.set_icon("assets/icon.ico");
        res.set("ProductName", "Yoink");
        res.set("FileDescription", "Yoink");
        res.set("CompanyName", "Ayoze Torres");
        res.set("LegalCopyright", "© 2026 Ayoze Torres");
        res.set("OriginalFilename", "yoink-desktop.exe");
        res.set("InternalName", "yoink-desktop");
        res.set("Comments", "https://github.com/ayozetr/yoink-app");
        res.set("ProductVersion", &ver);
        res.set("FileVersion", &ver);
        res.set_version_info(winresource::VersionInfo::PRODUCTVERSION, packed);
        res.set_version_info(winresource::VersionInfo::FILEVERSION, packed);
        if let Err(e) = res.compile() {
            println!("cargo:warning=failed to embed the Windows version resource: {e}");
        }
    }
}
