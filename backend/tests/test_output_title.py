"""Per-download filename title override (a single wrapped story/post item)."""

from __future__ import annotations

from app.models.media import DownloadRequest
from app.services.download_service import _apply_title_override, _build_options


def test_apply_title_override_passthrough_and_substitution():
    # No override: the template is untouched.
    assert _apply_title_override("%(title)s", None) == "%(title)s"
    assert _apply_title_override("%(title)s", "") == "%(title)s"
    # A plain title (no special chars) is substituted verbatim.
    assert _apply_title_override("%(title)s", "Story by X") == "Story by X"
    # It replaces only the title field, preserving the rest of a custom template.
    assert _apply_title_override("%(title)s [%(id)s]", "Story by X") == (
        "Story by X [%(id)s]"
    )


def test_apply_title_override_sanitizes_path_and_escapes_percent():
    # A path separator can't survive into the file name.
    assert "/" not in _apply_title_override("%(title)s", "A/B")
    # A literal % is escaped so yt-dlp treats it as text, not another field.
    assert _apply_title_override("%(title)s", "A%B") == "A%%B"


def test_build_options_uses_output_title_in_outtmpl(temp_dirs):
    noop = lambda _d: None  # noqa: E731 — trivial hook for the test
    req = DownloadRequest(
        url="https://x.com/v", kind="video", output_title="Story by X"
    )
    name_part = _build_options(req, noop)["outtmpl"].rsplit("/", 1)[-1]
    assert name_part == "Story by X.%(ext)s"
    assert "%(title)s" not in name_part  # the title token was replaced
