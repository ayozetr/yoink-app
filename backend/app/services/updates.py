"""Check the installed version against the latest GitHub release.

Uses stdlib urllib (no extra dependency). The GitHub API is unauthenticated
(60 requests/hour/IP) which is plenty for a local, user-triggered check.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.safe_http import SSL_CONTEXT
from app.models.media import ReleaseNotes, VersionInfo, WhatsNew

logger = logging.getLogger(__name__)

# Re-check GitHub for a newer release at most this often; between checks the
# cached result is served, so repeated launches don't burn the unauthenticated
# API budget (60 req/h/IP — shared across everything on the user's connection).
_UPDATE_CHECK_TTL = 3 * 3600


def _cache_path() -> Path:
    return settings.data_dir / "github_cache.json"


def _cache_read() -> dict[str, Any]:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _cache_get(key: str, max_age: float | None = None) -> Any | None:
    """The cached value for ``key``, or None. With ``max_age`` (seconds) a stale
    entry is treated as a miss; without it any age is returned (for immutable
    data, or as a last-resort fallback when the network fails)."""
    entry = _cache_read().get(key)
    if not isinstance(entry, dict) or "data" not in entry:
        return None
    if max_age is not None and time.time() - float(entry.get("at", 0)) > max_age:
        return None
    return entry["data"]


def _cache_set(key: str, data: Any) -> None:
    """Best-effort persist (atomic); never fatal if the cache can't be written."""
    try:
        settings.ensure_data_dir()
        cache = _cache_read()
        cache[key] = {"at": time.time(), "data": data}
        path = _cache_path()
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(cache), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("Could not write GitHub cache: %s", exc)


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


def _release_list(timeout: float = 8.0) -> list[dict]:
    """Every published release for the repo (newest first, per GitHub), or an
    empty list on any failure. Unauthenticated, so drafts aren't returned."""
    url = f"https://api.github.com/repos/{settings.github_repo}/releases?per_page=100"
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
        return []
    return data if isinstance(data, list) else []


def whats_new(current: str, since: str | None = None, timeout: float = 8.0) -> WhatsNew:
    """Release notes for every version in the range ``(since, current]``, newest
    first — so a user who skipped releases sees all of them, not just the latest.

    ``since`` is the version the app last ran as. When it's blank or not older
    than ``current`` (a fresh launch of the same version, or a downgrade) only
    this release is returned. Never raises: if the release list can't be fetched
    or yields nothing in range, it falls back to just the current release (and an
    empty ``entries`` when even that has no notes, so the popup simply hides)."""
    current_tag = current if current[:1].lower() == "v" else f"v{current}"

    # A released version's notes never change, so once fetched they're cached
    # indefinitely — repeat opens (and a later GitHub rate-limit) never re-fetch.
    cache_key = f"whatsnew:{since or ''}->{current}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return WhatsNew.model_validate(cached)

    def _single() -> WhatsNew:
        one = release_notes(current_tag, timeout)
        return WhatsNew(entries=[one] if one.notes else [])

    if not since or not _is_newer(current, since):
        result = _single()
    else:
        entries: list[ReleaseNotes] = []
        for rel in _release_list(timeout):
            if not isinstance(rel, dict) or rel.get("draft"):
                continue
            tag = rel.get("tag_name")
            if not isinstance(tag, str):
                continue
            # Keep only ``since < version <= current``.
            if _is_newer(tag, since) and not _is_newer(tag, current):
                body = rel.get("body")
                notes = _trim_notes(body) if isinstance(body, str) else None
                if notes:
                    entries.append(ReleaseNotes(version=tag, notes=notes))
        if entries:
            entries.sort(key=lambda e: _parse_version(e.version), reverse=True)
            result = WhatsNew(entries=entries)
        else:
            result = _single()

    # Only cache a real result — a rate-limited/empty fetch is retried next time.
    if result.entries:
        _cache_set(cache_key, result.model_dump())
    return result


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


def _version_from_cache(cached: dict[str, Any], current: str) -> VersionInfo:
    """Build a VersionInfo from a cached ``{latest, release_url}``, recomputing
    ``update_available`` against the *current* app version (which changes when the
    app self-updates, even though the cached GitHub data doesn't)."""
    latest = cached.get("latest")
    return VersionInfo(
        current=current,
        latest=latest if isinstance(latest, str) else None,
        update_available=bool(latest) and _is_newer(latest, current),
        release_url=cached.get("release_url"),
    )


def check_for_updates(timeout: float = 8.0) -> VersionInfo:
    """Latest GitHub release vs the current version. Cached for a few hours so
    repeated launches don't burn the API budget; on a network/rate-limit failure
    the last known result is served (stale) instead of an error, if we have one."""
    current = settings.app_version

    fresh = _cache_get("update_check", max_age=_UPDATE_CHECK_TTL)
    if fresh is not None:
        return _version_from_cache(fresh, current)

    url = f"https://api.github.com/repos/{settings.github_repo}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Yoink/{current}",
            "Accept": "application/vnd.github+json",
        },
    )

    def _stale_or(error: str) -> VersionInfo:
        stale = _cache_get("update_check")  # any age — better than an error
        if stale is not None:
            return _version_from_cache(stale, current)
        return VersionInfo(current=current, error=error)

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
        return _stale_or(message)
    except (urllib.error.URLError, TimeoutError, OSError):
        return _stale_or("Couldn't check for updates (offline?).")
    except (ValueError, json.JSONDecodeError):
        return _stale_or("Unexpected response from GitHub.")

    latest = data.get("tag_name")
    if not isinstance(latest, str):
        return _stale_or("No releases published yet.")

    release_url = data.get("html_url")
    release_url = release_url if isinstance(release_url, str) else None
    _cache_set("update_check", {"latest": latest, "release_url": release_url})
    return VersionInfo(
        current=current,
        latest=latest,
        update_available=_is_newer(latest, current),
        release_url=release_url,
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
