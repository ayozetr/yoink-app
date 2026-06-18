import { test, expect, type Page } from "@playwright/test";

const SETTINGS = {
  download_dir: "/home/u/Downloads/Yoink",
  default_kind: "video",
  default_quality: "1080p",
  cookies_from_browser: null,
  cookies_file: null,
};

const EMPTY_STATS = { total_downloads: 0, total_bytes: 0, transferred: "0 B" };

/** Mock the always-on calls the app makes on load (history, stats, settings). */
async function mockBase(
  page: Page,
  opts: { history?: unknown[]; stats?: unknown } = {},
) {
  const { history = [], stats = EMPTY_STATS } = opts;
  await page.route("**/api/history/stats", (route) =>
    route.fulfill({ json: stats }),
  );
  await page.route("**/api/history", (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({ status: 204, body: "" })
      : route.fulfill({ json: history }),
  );
  await page.route("**/api/settings", (route) => route.fulfill({ json: SETTINGS }));
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

test("opens the settings modal", async ({ page }) => {
  await mockBase(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Ajustes" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
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
