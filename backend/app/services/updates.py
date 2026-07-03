"""Check the installed version against the latest GitHub release.

Uses stdlib urllib (no extra dependency). The GitHub API is unauthenticated
(60 requests/hour/IP) which is plenty for a local, user-triggered check.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.core.config import settings
from app.core.safe_http import SSL_CONTEXT
from app.models.media import ReleaseNotes, VersionInfo


def _trim_notes(body: str) -> str:
    """Keep only the 'what's new' part — everything before the hidden
    ``<!-- /whatsnew -->`` marker, or failing that before the ``## Downloads``
    section, so the downloads table + self-update boilerplate stay on GitHub."""
    for cut in ("<!-- /whatsnew -->", "## Downloads"):
        index = body.find(cut)
        if index != -1:
            return body[:index].strip()
    return body.strip()


def release_notes(tag: str, timeout: float = 8.0) -> ReleaseNotes:
    """Fetch one release's markdown ``body`` (trimmed to the what's-new part) by
    tag — used by the after-update popup. Never raises: any failure returns
    ``notes=None`` so the popup simply doesn't show."""
    url = f"https://api.github.com/repos/{settings.github_repo}/releases/tags/{tag}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Yoink/{settings.app_version}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=SSL_CONTEXT
        ) as response:
            data = json.load(response)
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return ReleaseNotes(version=tag)
    body = data.get("body")
    notes = _trim_notes(body) if isinstance(body, str) else None
    return ReleaseNotes(version=tag, notes=notes)


def _parse_version(tag: str) -> tuple[int, ...]:
    """Turn a tag like 'v0.5.0' / '1.2.3-rc1' into a comparable tuple."""
    core = tag.lstrip("vV").split("+")[0].split("-")[0]
    parts: list[int] = []
    for piece in core.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


def check_for_updates(timeout: float = 8.0) -> VersionInfo:
    """Query the latest GitHub release and compare it to the current version."""
    current = settings.app_version
    url = f"https://api.github.com/repos/{settings.github_repo}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Yoink/{current}",
            "Accept": "application/vnd.github+json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            message = "GitHub API rate limit reached; try again later."
        elif exc.code == 404:
            message = "No public releases found (is the repo private?)."
        else:
            message = f"GitHub returned an error ({exc.code})."
        return VersionInfo(current=current, error=message)
    except (urllib.error.URLError, TimeoutError, OSError):
        return VersionInfo(
            current=current, error="Couldn't check for updates (offline?)."
        )
    except (ValueError, json.JSONDecodeError):
        return VersionInfo(current=current, error="Unexpected response from GitHub.")

    latest = data.get("tag_name")
    if not isinstance(latest, str):
        return VersionInfo(current=current, error="No releases published yet.")

    release_url = data.get("html_url")
    return VersionInfo(
        current=current,
        latest=latest,
        update_available=_is_newer(latest, current),
        release_url=release_url if isinstance(release_url, str) else None,
    )


def ytdlp_version() -> str:
    """The bundled yt-dlp version (date-based, e.g. '2024.12.23'), or 'unknown'."""
    try:
        from yt_dlp.version import __version__

        return __version__
    except Exception:  # noqa: BLE001 — never let a version read break the app
        return "unknown"


def check_ytdlp_update(timeout: float = 8.0) -> VersionInfo:
    """Compare the bundled yt-dlp against the latest yt-dlp GitHub release.

    Reuses VersionInfo: ``current`` is the bundled yt-dlp version, ``latest`` the
    newest published. This is informational only — Yoink ships yt-dlp inside the
    sidecar, so an update lands with the next Yoink release, not in-app.
    """
    current = ytdlp_version()
    url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Yoink/{settings.app_version}",
            "Accept": "application/vnd.github+json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        message = (
            "GitHub API rate limit reached; try again later."
            if exc.code == 403
            else f"GitHub returned an error ({exc.code})."
        )
        return VersionInfo(current=current, error=message)
    except (urllib.error.URLError, TimeoutError, OSError):
        return VersionInfo(current=current, error="Couldn't check (offline?).")
    except (ValueError, json.JSONDecodeError):
        return VersionInfo(current=current, error="Unexpected response from GitHub.")

    latest = data.get("tag_name")
    if not isinstance(latest, str):
        return VersionInfo(current=current, error="No releases found.")

    release_url = data.get("html_url")
    return VersionInfo(
        current=current,
        latest=latest,
        update_available=current != "unknown" and _is_newer(latest, current),
        release_url=release_url if isinstance(release_url, str) else None,
    )
