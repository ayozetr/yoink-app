// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! Minimal i18n for the native UI. `tl(lang, key)` returns a UI string; the table
//! is a flat match so adding a language is just another arm (and more locales can
//! be slotted in the same way the web UI ships 14). The language is auto-detected
//! from the environment and overridable in Ajustes.

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Lang {
    Es,
    En,
}

impl Lang {
    pub const ALL: [Lang; 2] = [Lang::Es, Lang::En];

    pub fn label(self) -> &'static str {
        match self {
            Lang::Es => "Español",
            Lang::En => "English",
        }
    }
}

/// Detect the language from `LANG`/`LC_ALL`/`LC_MESSAGES` (defaults to English).
pub fn detect() -> Lang {
    for var in ["LC_ALL", "LC_MESSAGES", "LANG"] {
        if let Ok(v) = std::env::var(var) {
            if v.to_lowercase().starts_with("es") {
                return Lang::Es;
            }
            if !v.is_empty() {
                return Lang::En;
            }
        }
    }
    Lang::En
}

/// Translate a key. Unknown keys fall back to the key itself (visible but safe).
pub fn tl(lang: Lang, key: &str) -> &str {
    use Lang::{En, Es};
    match (key, lang) {
        ("tab.inicio", Es) => "Inicio",
        ("tab.inicio", En) => "Home",
        ("tab.cola", Es) => "Cola",
        ("tab.cola", En) => "Queue",
        ("tab.historial", Es) => "Historial",
        ("tab.historial", En) => "History",
        ("tab.ajustes", Es) => "Ajustes",
        ("tab.ajustes", En) => "Settings",
        ("tab.logs", Es) => "Registro",
        ("tab.logs", En) => "Logs",
        ("logs.hint", Es) => "El registro de la app se mostrará aquí en una fase posterior.",
        ("logs.hint", En) => "The app log will show here in a later phase.",
        ("theme.toggle", Es) => "Cambiar tema",
        ("theme.toggle", En) => "Toggle theme",
        ("update.available", Es) => "Nueva versión disponible:",
        ("update.available", En) => "A new version is available:",
        ("update.view", Es) => "Ver",
        ("update.view", En) => "View",
        ("whatsnew.title", Es) => "Novedades",
        ("whatsnew.title", En) => "What's new",
        ("whatsnew.close", Es) => "Entendido",
        ("whatsnew.close", En) => "Got it",

        ("inicio.heading", Es) => "Pega un enlace para empezar",
        ("inicio.heading", En) => "Paste a link to begin",
        ("inicio.url_hint", Es) => "Pega aquí la URL del contenido, o busca",
        ("inicio.url_hint", En) => "Paste the content URL here, or search directly",
        ("inicio.preview", Es) => "PREVISUALIZACIÓN",
        ("inicio.preview", En) => "PREVIEW",
        ("inicio.empty_title", Es) => "Listo para descargar",
        ("inicio.empty_title", En) => "Ready to download",
        ("inicio.empty_sub", Es) => {
            "Pega un enlace arriba o escribe para buscar en YouTube o SoundCloud."
        }
        ("inicio.empty_sub", En) => "Paste a link above, or type to search YouTube or SoundCloud.",
        ("inicio.add_queue", Es) => "Añadir a la cola",
        ("inicio.add_queue", En) => "Add to queue",
        ("inicio.advanced", Es) => "Opciones avanzadas",
        ("inicio.advanced", En) => "Advanced options",
        ("inicio.available", Es) => "disponible",
        ("inicio.available", En) => "available",
        ("inicio.supported", Es) => "Sitios compatibles",
        ("inicio.supported", En) => "Supported sites",
        ("sites.title", Es) => "Webs soportadas",
        ("sites.title", En) => "Supported sites",
        ("sites.intro", Es) => "Plataformas verificadas.",
        ("sites.intro", En) => "Verified platforms.",
        ("sites.footer", Es) => "Y muchas más a través de yt-dlp.",
        ("sites.footer", En) => "And many more through yt-dlp.",
        ("inicio.analyze", Es) => "Analizar",
        ("inicio.analyze", En) => "Analyze",
        ("inicio.analyzing", Es) => "Analizando…",
        ("inicio.analyzing", En) => "Analyzing…",
        ("inicio.formats", Es) => "formatos",
        ("inicio.formats", En) => "formats",
        ("inicio.playlist", Es) => "Lista",
        ("inicio.playlist", En) => "Playlist",
        ("inicio.playlist_items", Es) => "elementos",
        ("inicio.playlist_items", En) => "items",
        ("inicio.playlist_soon", Es) => "La descarga de listas llega en una fase posterior.",
        ("inicio.playlist_soon", En) => "Playlist downloading comes in a later phase.",
        ("inicio.downloaded", Es) => "Descargado",
        ("inicio.downloaded", En) => "Downloaded",

        ("kind.video", Es) => "Vídeo",
        ("kind.video", En) => "Video",
        ("kind.audio", Es) => "Audio",
        ("kind.audio", En) => "Audio",
        ("field.quality", Es) => "Calidad",
        ("field.quality", En) => "Quality",
        ("field.container", Es) => "Contenedor",
        ("field.container", En) => "Container",
        ("field.format", Es) => "Formato",
        ("field.format", En) => "Format",
        ("field.audio", Es) => "Audio",
        ("field.audio", En) => "Audio",
        ("field.kind", Es) => "Tipo",
        ("field.kind", En) => "Kind",
        ("field.codec", Es) => "Códec",
        ("field.codec", En) => "Codec",
        ("field.subs", Es) => "Subtítulos",
        ("field.subs", En) => "Subtitles",
        ("field.chapters", Es) => "Capítulos",
        ("field.chapters", En) => "Chapters",
        ("adv.format", Es) => "Formato",
        ("adv.format", En) => "Format",
        ("adv.trim", Es) => "Recorte",
        ("adv.trim", En) => "Trim",
        ("action.download", Es) => "Descargar",
        ("action.download", En) => "Download",
        ("action.open", Es) => "Abrir",
        ("action.open", En) => "Open",
        ("action.refresh", Es) => "Refrescar",
        ("action.refresh", En) => "Refresh",
        ("action.copy", Es) => "Copiar",
        ("action.copy", En) => "Copy",
        ("action.export", Es) => "Exportar",
        ("action.export", En) => "Export",
        ("action.start", Es) => "Empezar",
        ("action.start", En) => "Start",
        ("action.save", Es) => "Guardar",
        ("action.save", En) => "Save",
        ("action.add", Es) => "Añadir",
        ("action.add", En) => "Add",
        ("state.saved", Es) => "Guardado",
        ("state.saved", En) => "Saved",
        ("state.loading", Es) => "Cargando…",
        ("state.loading", En) => "Loading…",

        ("cola.add_hint", Es) => "Pega enlaces (uno por línea)…",
        ("cola.add_hint", En) => "Paste links (one per line)…",
        ("cola.format", Es) => "FORMATO",
        ("cola.format", En) => "FORMAT",
        ("cola.running", Es) => "En curso",
        ("cola.running", En) => "Running",
        ("cola.empty", Es) => "Añade enlaces para empezar la cola.",
        ("cola.empty", En) => "Add links to start the queue.",
        ("cola.queued", Es) => "en cola",
        ("cola.queued", En) => "queued",
        ("cola.completed_n", Es) => "completadas",
        ("cola.completed_n", En) => "completed",
        ("cola.clear_done", Es) => "Limpiar completadas",
        ("cola.clear_done", En) => "Clear completed",
        ("cola.pending", Es) => "en espera",
        ("cola.pending", En) => "waiting",
        ("cola.done", Es) => "completada",
        ("cola.done", En) => "completed",
        ("cola.remove", Es) => "Quitar",
        ("cola.remove", En) => "Remove",

        ("hist.empty", Es) => "Todavía no hay descargas.",
        ("hist.empty", En) => "No downloads yet.",
        ("hist.downloads", Es) => "descargas",
        ("hist.downloads", En) => "downloads",
        ("hist.transferred", Es) => "transferido",
        ("hist.transferred", En) => "transferred",
        ("hist.search", Es) => "Buscar en el historial…",
        ("hist.search", En) => "Search history…",
        ("hist.thisweek", Es) => "ESTA SEMANA",
        ("hist.thisweek", En) => "THIS WEEK",
        ("time.now", Es) => "ahora",
        ("time.now", En) => "just now",

        ("set.theme", Es) => "Tema",
        ("set.theme", En) => "Theme",
        ("theme.dark", Es) => "Oscuro",
        ("theme.dark", En) => "Dark",
        ("theme.light", Es) => "Claro",
        ("theme.light", En) => "Light",
        ("set.onpage", Es) => "EN ESTA PÁGINA",
        ("set.onpage", En) => "ON THIS PAGE",
        ("set.general", Es) => "General",
        ("set.general", En) => "General",
        ("set.downloads", Es) => "Descargas",
        ("set.downloads", En) => "Downloads",
        ("set.dir", Es) => "Carpeta de descargas",
        ("set.dir", En) => "Download folder",
        ("set.potoken", Es) => "YouTube PO token",
        ("set.potoken", En) => "YouTube PO token",
        ("set.potoken_desc", Es) => {
            "auto mintea un token en un WebView oculto para saltar el muro antibot."
        }
        ("set.potoken_desc", En) => {
            "auto mints a token in a hidden WebView to clear the anti-bot wall."
        }
        ("set.mode", Es) => "Modo",
        ("set.mode", En) => "Mode",
        ("set.options", Es) => "Opciones",
        ("set.options", En) => "Options",
        ("set.normalize", Es) => "Normalizar audio a -14 LUFS",
        ("set.normalize", En) => "Normalize audio to -14 LUFS",
        ("set.sponsorblock", Es) => "SponsorBlock",
        ("set.sponsorblock", En) => "SponsorBlock",
        ("set.lyrics", Es) => "Buscar letras",
        ("set.lyrics", En) => "Fetch lyrics",
        ("set.updates", Es) => "Buscar actualizaciones al iniciar",
        ("set.updates", En) => "Check for updates on launch",
        ("set.notify", Es) => "Notificar al terminar",
        ("set.notify", En) => "Notify when done",
        ("set.language", Es) => "Idioma",
        ("set.language", En) => "Language",
        ("set.tray", Es) => "Minimizar a la bandeja al cerrar",
        ("set.tray", En) => "Minimize to tray on close",
        ("set.autostart", Es) => "Iniciar con el sistema",
        ("set.autostart", En) => "Launch at startup",
        ("set.quality", Es) => "Calidad",
        ("set.quality", En) => "Quality",
        ("set.bitrate", Es) => "Bitrate de audio",
        ("set.bitrate", En) => "Audio bitrate",
        ("set.vcodec", Es) => "Códec de vídeo",
        ("set.vcodec", En) => "Video codec",
        ("set.music_folders", Es) => "Carpetas de música (Artista/Álbum)",
        ("set.music_folders", En) => "Music folders (Artist/Album)",
        ("set.nfo", Es) => "Sidecars .nfo",
        ("set.nfo", En) => ".nfo sidecars",
        ("set.autotag", Es) => "Fuente de etiquetado",
        ("set.autotag", En) => "Auto-tag source",
        ("set.autotag_desc", Es) => {
            "Prueba Apple Music, luego Deezer y luego MusicBrainz hasta encontrar coincidencias."
        }
        ("set.autotag_desc", En) => {
            "Tries Apple Music, then Deezer, then MusicBrainz until it finds matches."
        }
        ("set.filename", Es) => "Plantilla de nombre",
        ("set.filename", En) => "Filename template",
        ("set.embed_subs", Es) => "Incrustar subtítulos por defecto",
        ("set.embed_subs", En) => "Embed subtitles by default",
        ("set.embed_chapters", Es) => "Incrustar capítulos por defecto",
        ("set.embed_chapters", En) => "Embed chapters by default",
        ("set.prefer_lossless", Es) => "Preferir lossless de SoundCloud",
        ("set.prefer_lossless", En) => "Prefer lossless from SoundCloud",
        ("set.loudness", Es) => "Objetivo de sonoridad",
        ("set.loudness", En) => "Loudness target",
        ("set.sb_enabled", Es) => "Activar SponsorBlock",
        ("set.sb_enabled", En) => "Enable SponsorBlock",
        ("set.sb_action", Es) => "Acción",
        ("set.sb_action", En) => "Action",
        ("set.network", Es) => "Red y acceso",
        ("set.network", En) => "Network & access",
        ("set.proxy", Es) => "Proxy",
        ("set.proxy", En) => "Proxy",
        ("set.ratelimit", Es) => "Límite de velocidad",
        ("set.ratelimit", En) => "Rate limit",
        ("set.cookies", Es) => "Cookies del navegador",
        ("set.cookies", En) => "Browser cookies",

        ("music.tracks", Es) => "pistas",
        ("music.tracks", En) => "tracks",
        ("music.import", Es) => "Importar todo",
        ("music.import", En) => "Import all",
        ("music.label", Es) => "IMPORTAR",
        ("music.label", En) => "IMPORT",
        ("music.songs", Es) => "canciones",
        ("music.songs", En) => "songs",
        ("music.download", Es) => "Descargar como audio",
        ("music.download", En) => "Download as audio",
        ("music.hint", Es) => {
            "Este audio no se puede bajar directamente — cada tema se busca en YouTube, se descarga y se etiqueta con los metadatos de la fuente."
        }
        ("music.hint", En) => {
            "This audio can't be downloaded directly — each track is matched on YouTube, downloaded, and tagged with the source metadata."
        }

        _ => key,
    }
}
