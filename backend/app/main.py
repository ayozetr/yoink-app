"""Yoink backend — FastAPI application entry point.

Run locally with:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import (
    autotag,
    download,
    history,
    info,
    media,
    settings as settings_router,
)
from app.services import history_store, settings_store


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="Local yt-dlp wrapper powering the Yoink media downloader.",
    )

    # The backend only ever listens on localhost, so allow any origin. This
    # avoids chasing the Tauri webview's per-platform origin scheme
    # (tauri://localhost on Linux/macOS, http://tauri.localhost on Windows).
    # No credentials/cookies are used, so the wildcard is safe.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Apply persisted settings overrides and ensure the history DB exists.
    settings_store.load_overrides()
    history_store.init_db()

    app.include_router(info.router, prefix=settings.api_prefix)
    app.include_router(media.router, prefix=settings.api_prefix)
    app.include_router(download.router, prefix=settings.api_prefix)
    app.include_router(history.router, prefix=settings.api_prefix)
    app.include_router(settings_router.router, prefix=settings.api_prefix)
    app.include_router(autotag.router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"], summary="Liveness probe")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
