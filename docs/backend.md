# Backend

Python + FastAPI, wrapping yt-dlp. Strictly typed throughout.

## Structure

```
backend/
├── app/
│   ├── main.py                 # app factory: FastAPI(), CORS, router mounting, /health
│   ├── core/
│   │   └── config.py           # typed Settings (CORS origins, download dir) via pydantic-settings
│   ├── models/
│   │   └── media.py            # Pydantic models: InfoRequest, MediaFormat, VideoInfo
│   ├── routers/
│   │   └── info.py             # POST /api/info
│   └── services/
│       └── ytdlp_service.py    # typed yt-dlp wrapper (extract_info, download=False)
└── requirements.txt
```

## The yt-dlp wrapper

`services/ytdlp_service.py` is the only place that touches yt-dlp:

- `extract_info(url)` runs `YoutubeDL.extract_info(url, download=False)`, then
  `sanitize_info` to get a stable, JSON-serializable dict.
- Helpers map raw yt-dlp fields into the typed `VideoInfo` / `MediaFormat`
  models: `_map_format` (codecs → has_video/has_audio, filesize), `_best_thumbnail`,
  `_format_duration` (seconds → `"1h 24m 18s"`).
- Failures raise `MediaExtractionError`, which the route turns into HTTP 422.

## API

### `GET /health`

Liveness probe → `{ "status": "ok", "app": "Yoink Backend" }`.

### `POST /api/info`

Request body (`InfoRequest`):

```json
{ "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }
```

Response (`VideoInfo`, abridged):

```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "duration": 213.0,
  "duration_string": "3:33",
  "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
  "formats": [
    { "format_id": "137", "ext": "mp4", "resolution": "1080p", "has_video": true, "has_audio": false }
  ]
}
```

- Invalid URL → `422` from Pydantic validation.
- Extraction failure → `422` with `detail: "Could not extract media info: …"`.

## Configuration

`YOINK_`-prefixed env vars (or a local `.env`):

| Variable             | Default                 | Description                   |
| -------------------- | ----------------------- | ----------------------------- |
| `YOINK_CORS_ORIGINS` | Vite dev server origins | Allowed CORS origins          |
| `YOINK_DOWNLOAD_DIR` | `~/Downloads/Yoink`     | Where media is written        |
| `YOINK_API_PREFIX`   | `/api`                  | API route prefix              |

## Run

```bash
cd backend
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload      # http://127.0.0.1:8000  (Swagger UI at /docs)
```

## Next

Download + live progress over WebSockets/SSE, plus tests — see the
[roadmap](ROADMAP.md), Phase 1-3.
