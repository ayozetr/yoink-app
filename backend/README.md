# Yoink Backend

Local FastAPI service that wraps [yt-dlp](https://github.com/yt-dlp/yt-dlp) to
power the Yoink frontend. It extracts media metadata over REST and (later) will
stream download progress to the UI via WebSockets/SSE.

## Requirements

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) on your `PATH` (needed to merge high-quality
  video + audio formats during downloads)

## Setup

```bash
cd backend
python -m venv .venv

# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

- API base: `http://127.0.0.1:8000/api`
- Interactive docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

## Endpoints

### `POST /api/info`

Extract metadata for a URL **without downloading** (`yt-dlp` `download=False`).

Request:

```json
{ "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }
```

Response (abridged):

```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "duration": 213.0,
  "duration_string": "3:33",
  "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
  "formats": [{ "format_id": "137", "ext": "mp4", "resolution": "1080p", "has_video": true, "has_audio": false }]
}
```

## Configuration

Settings are read from `YOINK_`-prefixed environment variables (or a local
`.env`):

| Variable               | Default                  | Description                          |
| ---------------------- | ------------------------ | ------------------------------------ |
| `YOINK_CORS_ORIGINS`   | Vite dev server origins  | JSON list of allowed origins         |
| `YOINK_DOWNLOAD_DIR`   | `~/Downloads/Yoink`      | Where downloaded media is written    |

## Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router mounting
│   ├── core/config.py       # typed settings (CORS, paths)
│   ├── models/media.py      # Pydantic models (JSON contract)
│   ├── routers/info.py      # /api/info route
│   └── services/ytdlp_service.py  # typed yt-dlp wrapper
└── requirements.txt
```
