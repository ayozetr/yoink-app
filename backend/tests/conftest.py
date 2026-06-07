"""Shared pytest fixtures.

Critically, history tests must NEVER touch the real DB at ~/.yoink — every
fixture points `settings.data_dir` (and `download_dir`) at a tmp_path.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import history_store


@pytest.fixture
def temp_dirs(tmp_path, monkeypatch):
    """Isolate data_dir and download_dir to a temp location for a test."""
    data_dir = tmp_path / "data"
    download_dir = tmp_path / "downloads"
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "download_dir", download_dir)
    # Pin mutable settings so any in-test mutation (e.g. via the settings store)
    # is reverted at teardown and never leaks into other tests.
    monkeypatch.setattr(settings, "default_kind", settings.default_kind)
    monkeypatch.setattr(settings, "default_quality", settings.default_quality)
    monkeypatch.setattr(settings, "cookies_from_browser", settings.cookies_from_browser)
    monkeypatch.setattr(settings, "cookies_file", settings.cookies_file)
    monkeypatch.setattr(settings, "proxy", settings.proxy)
    monkeypatch.setattr(settings, "filename_template", settings.filename_template)
    monkeypatch.setattr(settings, "rate_limit", settings.rate_limit)
    monkeypatch.setattr(settings, "video_codec", settings.video_codec)
    monkeypatch.setattr(settings, "audio_bitrate", settings.audio_bitrate)
    monkeypatch.setattr(settings, "sponsorblock_enabled", settings.sponsorblock_enabled)
    monkeypatch.setattr(settings, "sponsorblock_action", settings.sponsorblock_action)
    return tmp_path


@pytest.fixture
def history_db(temp_dirs):
    """A freshly-initialized, empty history database in a temp dir."""
    history_store.init_db()
    return temp_dirs
