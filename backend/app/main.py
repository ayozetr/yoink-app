"""Yoink backend — FastAPI application entry point.

Run locally with:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import download, history, info
from app.services import history_store


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        summary="Local yt-dlp wrapper powering the Yoink media downloader.",
    )

    # Allow the local Vite frontend to call the API.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Ensure the history database exists before serving requests.
    history_store.init_db()

    app.include_router(info.router, prefix=settings.api_prefix)
    app.include_router(download.router, prefix=settings.api_prefix)
    app.include_router(history.router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"], summary="Liveness probe")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
