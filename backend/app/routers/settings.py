"""`/api/settings` — read and update user-editable settings."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.media import AppSettings, VersionInfo
from app.services import settings_store, updates

router = APIRouter(tags=["settings"])


@router.get("/version", response_model=VersionInfo, summary="Version + update check")
def get_version() -> VersionInfo:
    """Return the current version and whether a newer GitHub release exists."""
    return updates.check_for_updates()


@router.get("/settings", response_model=AppSettings, summary="Current settings")
def get_settings() -> AppSettings:
    """Return the effective settings (env defaults + persisted overrides)."""
    return settings_store.get_current()


@router.put("/settings", response_model=AppSettings, summary="Update settings")
def put_settings(payload: AppSettings) -> AppSettings:
    """Apply and persist new settings; returns the effective snapshot."""
    return settings_store.update(payload)
