"""Default download dir resolves the OS Downloads folder regardless of locale."""

from __future__ import annotations

import sys
from pathlib import Path

from app.core import config


def test_xdg_download_dir_localized(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "user-dirs.dirs").write_text(
        '# generated\nXDG_DOWNLOAD_DIR="$HOME/Descargas"\n', encoding="utf-8"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    assert config._xdg_download_dir() == Path.home() / "Descargas"


def test_xdg_download_dir_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
    assert config._xdg_download_dir() is None


def test_windows_download_dir_noop_off_windows():
    if sys.platform != "win32":
        assert config._windows_download_dir() is None


def test_default_download_dir_under_downloads_and_yoink():
    default = config._default_download_dir()
    assert default.name == "Yoink"
    # The parent is the resolved Downloads folder (localized on Linux).
    assert default.parent == config._downloads_dir()
