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
    return tmp_path


@pytest.fixture
def history_db(temp_dirs):
    """A freshly-initialized, empty history database in a temp dir."""
    history_store.init_db()
    return temp_dirs
