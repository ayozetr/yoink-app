import { test, expect, type Page } from "@playwright/test";

const SETTINGS = {
  download_dir: "/home/u/Downloads/Yoink",
  default_kind: "video",
  default_quality: "1080p",
  cookies_from_browser: null,
  cookies_file: null,
  check_updates: false,
  notify_on_complete: true,
};

const EMPTY_STATS = { total_downloads: 0, total_bytes: 0, transferred: "0 B" };

/** Mock the always-on calls the app makes on load (history, stats, settings). */
async function mockBase(
  page: Page,
  opts: { history?: unknown[]; stats?: unknown; settings?: unknown } = {},
) {
  const { history = [], stats = EMPTY_STATS, settings = SETTINGS } = opts;
  await page.route("**/api/history/stats", (route) =>
    route.fulfill({ json: stats }),
  );
  await page.route("**/api/history", (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({ status: 204, body: "" })
      : route.fulfill({ json: history }),
  );
  await page.route("**/api/settings", (route) => route.fulfill({ json: settings }));
}

const VIDEO_INFO = {
  type: "video",
  playlist: null,
  video: {
    id: "abc",
    title: "My Test Video",
    duration: 61,
    duration_string: "1m 1s",
    uploader: "Test Channel",
    thumbnail_url: null,
    webpage_url: null,
    extractor: "youtube",
    formats: [
      {
        format_id: "18",
        ext: "mp4",
        resolution: "1280x720",
        fps: 30,
        vcodec: "avc1",
        acodec: "mp4a",
        filesize: 1000,
        has_video: true,
        has_audio: true,
      },
    ],
    source_lossless: false,
    best_audio_abr: null,
    subtitle_langs: [],
    auto_caption_langs: [],
    has_chapters: false,
    audio_langs: [],
  },
};

/** Same as VIDEO_INFO but flagged as immersive (VR) — seeds the auto-expand. */
const VR_VIDEO_INFO = {
  ...VIDEO_INFO,
  video: { ...VIDEO_INFO.video, id: "vr1", title: "My VR Video", is_vr: true, vr_layout: "180_sbs" },
};

const PLAYLIST_INFO = {
  type: "playlist",
  video: null,
  playlist: {
    id: "PL1",
    title: "My Playlist",
    uploader: "Me",
    entry_count: 2,
    truncated: false,
    entries: [
      { id: "a", title: "First Clip", url: "http://x/a", duration_string: "1:00", thumbnail_url: null, uploader: null },
      { id: "b", title: "Second Clip", url: "http://x/b", duration_string: "2:00", thumbnail_url: null, uploader: null },
    ],
  },
};

test("shows the empty history state on load", async ({ page }) => {
  await mockBase(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Media Downloader" }),
  ).toBeVisible();
  await expect(page.getByText("Aún no hay descargas. Analiza una URL para empezar.")).toBeVisible();
});

test("analyzes a single video into a preview", async ({ page }) => {
  await mockBase(page);
  await page.route("**/api/info", (route) => route.fulfill({ json: VIDEO_INFO }));

  await page.goto("/");
  await page.getByPlaceholder(/Pega aquí la URL/).fill("https://x.com/v");
  await page.getByRole("button", { name: "Analizar" }).click();

  await expect(page.getByRole("heading", { name: "My Test Video" })).toBeVisible();
  await expect(page.getByText("Vista previa")).toBeVisible();
  await expect(page.getByText("Test Channel")).toBeVisible();
});

test("saves and shows a download preset", async ({ page }) => {
  await mockBase(page);
  await page.route("**/api/info", (route) => route.fulfill({ json: VIDEO_INFO }));

  await page.goto("/");
  await page.getByPlaceholder(/Pega aquí la URL/).fill("https://x.com/v");
  await page.getByRole("button", { name: "Analizar" }).click();
  await expect(page.getByRole("heading", { name: "My Test Video" })).toBeVisible();

  // Save the current selection as a named preset → a chip appears for it.
  await page.getByRole("button", { name: "Guardar preset" }).click();
  await page.getByPlaceholder("Nombre del preset").fill("My Preset");
  await page.getByRole("button", { name: "Guardar", exact: true }).click();
  await expect(page.getByRole("button", { name: "My Preset" })).toBeVisible();
});

test("collapses secondary controls under Advanced options", async ({ page }) => {
  await mockBase(page);
  await page.route("**/api/info", (route) => route.fulfill({ json: VIDEO_INFO }));

  await page.goto("/");
  await page.getByPlaceholder(/Pega aquí la URL/).fill("https://x.com/v");
  await page.getByRole("button", { name: "Analizar" }).click();
  await expect(page.getByRole("heading", { name: "My Test Video" })).toBeVisible();

  // Trim lives under "Opciones avanzadas" — hidden until the toggle is opened.
  await expect(page.getByRole("button", { name: "Recortar" })).toHaveCount(0);
  await page.getByRole("button", { name: "Opciones avanzadas" }).click();
  await expect(page.getByRole("button", { name: "Recortar" })).toBeVisible();
});

test("auto-expands Advanced options for a VR video", async ({ page }) => {
  await mockBase(page);
  await page.route("**/api/info", (route) => route.fulfill({ json: VR_VIDEO_INFO }));

  await page.goto("/");
  await page.getByPlaceholder(/Pega aquí la URL/).fill("https://x.com/vr");
  await page.getByRole("button", { name: "Analizar" }).click();
  await expect(page.getByRole("heading", { name: "My VR Video" })).toBeVisible();

  // VR is detected, so the advanced section opens itself: trim + the VR toggle
  // are visible with no click.
  await expect(page.getByRole("button", { name: "Recortar" })).toBeVisible();
  await expect(page.getByText("VR (inmersivo)")).toBeVisible();
});

test("analyzes a playlist with per-item selection", async ({ page }) => {
  await mockBase(page);
  await page.route("**/api/info", (route) => route.fulfill({ json: PLAYLIST_INFO }));

  await page.goto("/");
  await page.getByPlaceholder(/Pega aquí la URL/).fill("https://x.com/list");
  await page.getByRole("button", { name: "Analizar" }).click();

  await expect(page.getByText("My Playlist")).toBeVisible();
  await expect(page.getByText("First Clip")).toBeVisible();
  await expect(page.getByText("Second Clip")).toBeVisible();
  // Both items selected by default -> button shows (2).
  await expect(page.getByRole("button", { name: /Descargar \(2\)/ })).toBeVisible();

  // Deselect one item (by name, so the chapters checkbox doesn't interfere).
  await page.getByRole("checkbox", { name: /First Clip/ }).uncheck();
  await expect(page.getByRole("button", { name: /Descargar \(1\)/ })).toBeVisible();
});

test("playlist sync: pre-selects only items you don't already have", async ({ page }) => {
  await mockBase(page);
  const info = {
    type: "playlist",
    video: null,
    playlist: {
      id: "PL9",
      title: "Sync List",
      uploader: "Me",
      entry_count: 2,
      truncated: false,
      entries: [
        { id: "a", title: "Old Clip", url: "http://x/a", duration_string: "1:00", thumbnail_url: null, uploader: null, already_downloaded: true },
        { id: "b", title: "New Clip", url: "http://x/b", duration_string: "2:00", thumbnail_url: null, uploader: null, already_downloaded: false },
      ],
    },
  };
  await page.route("**/api/info", (route) => route.fulfill({ json: info }));

  await page.goto("/");
  await page.getByPlaceholder(/Pega aquí la URL/).fill("https://x.com/synclist");
  await page.getByRole("button", { name: "Analizar" }).click();

  await expect(page.getByText("Sync List")).toBeVisible();
  // Only the new one is pre-selected (button shows 1); the old one is badged "off".
  await expect(page.getByRole("button", { name: /Descargar \(1\)/ })).toBeVisible();
  await expect(page.getByText("Descargada")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /New Clip/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /Old Clip/ })).not.toBeChecked();
});

test("hides the video/audio selector for a YouTube Music playlist", async ({ page }) => {
  await mockBase(page);
  await page.route("**/api/info", (route) => route.fulfill({ json: PLAYLIST_INFO }));

  await page.goto("/");
  await page
    .getByPlaceholder(/Pega aquí la URL/)
    .fill("https://music.youtube.com/playlist?list=PL1");
  await page.getByRole("button", { name: "Analizar" }).click();

  await expect(page.getByText("My Playlist")).toBeVisible();
  // Audio-only: the format picker is the audio one, no Vídeo/Audio kind selector,
  // and the count reads "canciones" (songs), not "vídeos".
  await expect(page.getByLabel("Formato de audio")).toBeVisible();
  await expect(page.getByLabel("Formato", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/2 canciones/)).toBeVisible();
});

const MUSIC_INFO = {
  source: "spotify",
  type: "playlist",
  name: "My Mix",
  subtitle: "Some Owner",
  cover_url: null,
  truncated: false,
  tracks: Array.from({ length: 10 }, (_, i) => ({
    title: `Track ${i + 1}`,
    artists: "Artist",
    duration_ms: 200000,
    is_explicit: false,
    album: "Album",
    year: "2024",
    cover_url: null,
    source_url: `https://open.spotify.com/track/${i}`,
  })),
};

test("imports a music playlist with shift-click range selection", async ({ page }) => {
  await mockBase(page);
  await page.route("**/api/music/resolve", (route) =>
    route.fulfill({ json: MUSIC_INFO }),
  );

  await page.goto("/");
  await page
    .getByPlaceholder(/Pega aquí la URL/)
    .fill("https://open.spotify.com/playlist/abc");
  await page.getByRole("button", { name: "Analizar" }).click();

  // Generic "Importar" label; the source now leads the meta line ("Spotify • N …").
  await expect(page.getByText(/Spotify • \d+/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "My Mix" })).toBeVisible();
  // All 10 selected by default → the duration summary and the import count.
  await expect(page.getByText("10 seleccionados")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Importar 10 como audio" }),
  ).toBeVisible();

  // Plain-click a row to deselect it, then Shift+click 3 rows down to clear the
  // whole range (tracks 3-6) at once.
  await page.getByText("Track 3", { exact: true }).click();
  await page.getByText("Track 6", { exact: true }).click({ modifiers: ["Shift"] });
  await expect(
    page.getByRole("button", { name: "Importar 6 como audio" }),
  ).toBeVisible();
});

test("keeps a '0 selected' summary after deselecting everything", async ({ page }) => {
  await mockBase(page);
  await page.route("**/api/music/resolve", (route) =>
    route.fulfill({ json: MUSIC_INFO }),
  );

  await page.goto("/");
  await page
    .getByPlaceholder(/Pega aquí la URL/)
    .fill("https://open.spotify.com/playlist/abc");
  await page.getByRole("button", { name: "Analizar" }).click();
  await expect(page.getByRole("heading", { name: "My Mix" })).toBeVisible();

  // Deselecting everything keeps the summary line (it used to vanish) reading "0 …".
  await page.getByRole("button", { name: "Deseleccionar todo" }).click();
  await expect(page.getByText("0 seleccionados · 0min")).toBeVisible();
});

test("queue: drag reorders items", async ({ page }) => {
  await mockBase(page);
  // Non-music URLs are resolved via /api/info on add; a 422 makes each fall back
  // to a plain single titled with its URL (which the test drags by).
  await page.route("**/api/info", (route) =>
    route.fulfill({ status: 422, json: { detail: "x" } }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Cola de descargas" }).click();
  await page
    .getByPlaceholder(/enlaces/i)
    .first()
    .fill("http://x/1\nhttp://x/2\nhttp://x/3");
  await page.getByRole("button", { name: /Añadir/ }).click();

  const items = page.getByRole("listitem");
  await expect(items).toHaveCount(3);
  await expect(items.nth(0)).toContainText("http://x/1");
  // Drag the last item onto the first → it moves to the top.
  await items.nth(2).dragTo(items.nth(0));
  await expect(items.nth(0)).toContainText("http://x/3");
});

test("queue: a music album adds as an expandable, selectable group", async ({
  page,
}) => {
  await mockBase(page);
  // A Spotify album resolves (keylessly) into a tracklist.
  await page.route("**/api/music/resolve", (route) =>
    route.fulfill({
      json: {
        source: "spotify",
        type: "album",
        name: "Greatest Hits",
        subtitle: "The Band",
        cover_url: null,
        truncated: false,
        tracks: [
          { title: "Song A", artists: "The Band", duration_ms: null, is_explicit: false, album: "Greatest Hits", year: "2020", cover_url: null, source_url: "s://a" },
          { title: "Song B", artists: "The Band", duration_ms: null, is_explicit: false, album: "Greatest Hits", year: "2020", cover_url: null, source_url: "s://b" },
          { title: "Song C", artists: "The Band", duration_ms: null, is_explicit: false, album: "Greatest Hits", year: "2020", cover_url: null, source_url: "s://c" },
        ],
      },
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Cola de descargas" }).click();
  await page
    .getByPlaceholder(/enlaces/i)
    .first()
    .fill("https://open.spotify.com/album/123");
  await page.getByRole("button", { name: /Añadir/ }).click();

  // The album is a single row (not 3) that expands into its 3 tracks.
  await expect(page.getByText("Greatest Hits")).toBeVisible();
  await expect(page.getByText("Spotify · 3/3")).toBeVisible();
  await expect(page.getByText("Song B")).toHaveCount(0); // collapsed
  await page.getByRole("button", { name: "Desplegar" }).click();
  await expect(page.getByText("Song B")).toBeVisible();

  // Deselect one track → the counter drops to 2/3.
  await page.getByRole("checkbox").nth(1).uncheck();
  await expect(page.getByText("Spotify · 2/3")).toBeVisible();
});

test("update experience: settings toggle opens the What's new popup", async ({
  page,
}) => {
  await mockBase(page);
  await page.route("**/api/release-notes", (route) =>
    route.fulfill({
      json: {
        version: "v2.6.0",
        notes: "## New stuff\n\n- **Bold** thing\n- Another one",
      },
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Ajustes" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // The opt-in "check automatically" toggle lives in the General category.
  await dialog.getByRole("button", { name: "General" }).click();
  await expect(
    dialog.getByText("Comprobar actualizaciones automáticamente"),
  ).toBeVisible();
  // "Ver novedades" lives in the About category and opens the popup.
  await dialog.getByRole("button", { name: "Acerca de" }).click();
  await dialog.getByRole("button", { name: "Ver novedades" }).click();
  await expect(page.getByRole("heading", { name: "New stuff" })).toBeVisible();
  await expect(page.getByText("Bold")).toBeVisible();
});

test("history: action buttons don't stick visible after a mouse click", async ({ page }) => {
  const entry = {
    id: 1, title: "Sticky Test Song", url: "http://x/s", kind: "audio", status: "completed",
    filename: "Sticky Test Song.mp3", filepath: "/dl/Sticky Test Song.mp3", filesize: 1000,
    quality: "320 kbps", error_message: null, created_at: "2026-01-01T00:00:00Z", mtime: null,
  };
  await mockBase(page, { history: [entry] });
  await page.route("**/api/open", (route) => route.fulfill({ status: 200, json: { ok: true } }));
  await page.goto("/");

  const openFolder = page.getByRole("button", { name: "Abrir carpeta" });
  const actions = openFolder.locator("xpath=..");
  const box = (await openFolder.boundingBox())!;
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;

  // Move the pointer over the row (the actions live inside the group) -> fade in.
  await page.mouse.move(cx, cy);
  await expect(actions).toHaveCSS("opacity", "1");
  // Click with the mouse, then move the pointer off the row entirely.
  await page.mouse.down();
  await page.mouse.up();
  await page.mouse.move(5, 5);
  // The bug: focus-within kept them at opacity 1 after the click. Now they fade out.
  await expect(actions).toHaveCSS("opacity", "0");
});

test("opens the settings modal", async ({ page }) => {
  await mockBase(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Ajustes" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // General opens by default; the download dir lives in the Downloads category.
  await dialog.getByRole("button", { name: "Descargas" }).click();
  await expect(dialog.getByText("Carpeta para descargas")).toBeVisible();
  // The download-dir input is seeded from the mocked settings.
  await expect(dialog.locator("input").first()).toHaveValue(
    "/home/u/Downloads/Yoink",
  );
});

test("offers to resume an unfinished batch", async ({ page }) => {
  await mockBase(page);
  // Seed a batch left half-done (1 of 2) before the app boots.
  await page.addInitScript(() => {
    localStorage.setItem(
      "yoink-batch",
      JSON.stringify({
        jobs: [
          { request: { url: "http://x/a", kind: "audio" }, title: "Track A" },
          { request: { url: "http://x/b", kind: "audio" }, title: "Track B" },
        ],
        done: 1,
      }),
    );
  });
  await page.goto("/");

  // One pending item → the resume banner appears; Discard clears it.
  await expect(page.getByRole("button", { name: "Reanudar" })).toBeVisible();
  await page.getByRole("button", { name: "Descartar" }).click();
  await expect(page.getByRole("button", { name: "Reanudar" })).toHaveCount(0);
});

// A completed audio download — its history card has a "re-tag" (Etiquetar audio)
// button that opens the auto-tag dialog, where the lyrics gating lives.
const AUDIO_HISTORY = [
  {
    id: 1,
    title: "Some Song",
    url: "http://x/song",
    kind: "audio",
    status: "completed",
    filename: "Some Song.mp3",
    filepath: "/x/Some Song.mp3",
    filesize: 100,
    created_at: "2026-01-01T00:00:00Z",
  },
];
const AUDIO_STATS = { total_downloads: 1, total_bytes: 100, transferred: "100 B" };

// Identify returns a single match so the panel reaches the "review" stage with
// the title field seeded (which is what triggers the lyrics lookup).
const TAG_CANDIDATES = {
  results: [
    {
      title: "Some Song",
      artist: "Some Artist",
      album: "Some Album",
      year: "2024",
      track_number: 1,
      cover_url: null,
    },
  ],
};
const LYRICS_FOUND = {
  found: true,
  instrumental: false,
  has_synced: false,
  plain: "la la la",
};

test("hides the lyrics searcher when fetch-lyrics is off", async ({ page }) => {
  await mockBase(page, {
    history: AUDIO_HISTORY,
    stats: AUDIO_STATS,
    settings: { ...SETTINGS, fetch_lyrics: false },
  });
  await page.route("**/api/autotag/identify", (route) =>
    route.fulfill({ json: TAG_CANDIDATES }),
  );
  // If the gate works, the lyrics endpoint is never even hit.
  let lyricsCalls = 0;
  await page.route("**/api/autotag/lyrics", (route) => {
    lyricsCalls += 1;
    return route.fulfill({ json: LYRICS_FOUND });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Etiquetar audio" }).first().click();

  // Reaches the review stage: the title field is seeded from the identify match.
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("textbox").first()).toHaveValue("Some Song");

  // No lyrics block (neither the "searching" nor the "found" state) is rendered.
  await expect(dialog.getByText("Buscando letra…")).toHaveCount(0);
  await expect(dialog.getByText("Encontrada (LRCLIB)")).toHaveCount(0);
  // Give the (gated) debounced lookup well past its 400ms window to (not) fire,
  // then assert it never reached the network.
  await page.waitForTimeout(700);
  expect(lyricsCalls).toBe(0);
});

test("shows the lyrics searcher when fetch-lyrics is on", async ({ page }) => {
  await mockBase(page, {
    history: AUDIO_HISTORY,
    stats: AUDIO_STATS,
    settings: { ...SETTINGS, fetch_lyrics: true },
  });
  await page.route("**/api/autotag/identify", (route) =>
    route.fulfill({ json: TAG_CANDIDATES }),
  );
  await page.route("**/api/autotag/lyrics", (route) =>
    route.fulfill({ json: LYRICS_FOUND }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Etiquetar audio" }).first().click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("textbox").first()).toHaveValue("Some Song");
  // With the feature on, the debounced LRCLIB lookup runs and its result shows.
  await expect(dialog.getByText("Encontrada (LRCLIB)")).toBeVisible();
});

test("re-analyzes a history item into a fresh preview", async ({ page }) => {
  await mockBase(page, {
    history: [
      {
        id: 1,
        title: "Old Download",
        url: "https://x.com/v",
        kind: "video",
        status: "completed",
        filename: "Old.mp4",
        filepath: "/x/Old.mp4",
        filesize: 100,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    stats: { total_downloads: 1, total_bytes: 100, transferred: "100 B" },
  });
  await page.route("**/api/info", (route) => route.fulfill({ json: VIDEO_INFO }));

  await page.goto("/");
  await page.getByRole("button", { name: "Volver a analizar" }).click();
  // The history row's URL is re-analyzed and the preview appears in the main column.
  await expect(page.getByRole("heading", { name: "My Test Video" })).toBeVisible();
});

test("analyzes a link dropped onto the window", async ({ page }) => {
  await mockBase(page);
  await page.route("**/api/info", (route) => route.fulfill({ json: VIDEO_INFO }));

  await page.goto("/");
  // Wait until the app has mounted (so the window drop listener is attached)
  // before dispatching — otherwise the event fires into the void.
  await expect(page.getByPlaceholder(/Pega aquí la URL/)).toBeVisible();
  // Dispatch a synthetic drop carrying a URL (as a dragged hyperlink would).
  // Chromium's DragEvent constructor drops the `dataTransfer` init, so attach it
  // explicitly — a real OS drop populates it natively.
  await page.evaluate(() => {
    const dt = new DataTransfer();
    dt.setData("text/uri-list", "https://x.com/dropped");
    const ev = new DragEvent("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(ev, "dataTransfer", { value: dt });
    window.dispatchEvent(ev);
  });
  await expect(page.getByRole("heading", { name: "My Test Video" })).toBeVisible();
});

test("clears the history", async ({ page }) => {
  await mockBase(page, {
    history: [
      {
        id: 1,
        title: "Old Download",
        url: "http://x",
        kind: "audio",
        status: "completed",
        filename: "Old Download.mp3",
        filepath: "/x/Old Download.mp3",
        filesize: 100,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    stats: { total_downloads: 1, total_bytes: 100, transferred: "100 B" },
  });

  await page.goto("/");
  await expect(page.getByText("Old Download")).toBeVisible();

  const deleteRequest = page.waitForRequest(
    (req) => req.url().includes("/api/history") && req.method() === "DELETE",
  );
  // Clearing is destructive: the first click only arms a confirm, the second
  // (on the "¿Confirmar?" button) actually clears.
  await page.getByRole("button", { name: "Limpiar" }).click();
  await page.getByRole("button", { name: "¿Confirmar?" }).click();
  await deleteRequest;
});
