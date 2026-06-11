"""Trim/clip range guards: the model validator + the download-options branch."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.media import DownloadRequest


def test_inverted_trim_range_rejected():
    with pytest.raises(ValidationError):
        DownloadRequest(url="https://x.com/v", trim_start=100, trim_end=10)
    with pytest.raises(ValidationError):
        DownloadRequest(url="https://x.com/v", trim_start=10, trim_end=10)


def test_download_request_accepts_auto_vr():
    # The queue sets auto_vr (no preview) instead of an explicit is_vr.
    req = DownloadRequest(url="https://x.com/v", kind="video", auto_vr=True)
    assert req.auto_vr is True
    assert req.is_vr is False


def test_valid_and_open_trim_ranges_accepted():
    DownloadRequest(url="https://x.com/v", trim_start=10, trim_end=100)
    DownloadRequest(url="https://x.com/v", trim_start=30)  # open end
    # A bare trim_end=0 (e.g. a UI reset) is allowed by the model; the download
    # layer treats it as "no end" (see below).
    DownloadRequest(url="https://x.com/v", trim_end=0)


def test_build_options_treats_zero_trim_end_as_no_trim(temp_dirs):
    from app.services.download_service import _build_options

    noop = lambda _d: None  # noqa: E731 — trivial hook for the test
    zero = DownloadRequest(url="https://x.com/v", kind="video", trim_end=0)
    assert "download_ranges" not in _build_options(zero, noop)

    real = DownloadRequest(url="https://x.com/v", kind="video", trim_start=5, trim_end=10)
    opts = _build_options(real, noop)
    assert "download_ranges" in opts and opts.get("force_keyframes_at_cuts") is True
