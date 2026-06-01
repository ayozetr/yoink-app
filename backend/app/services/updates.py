"""Check the installed version against the latest GitHub release.

Uses stdlib urllib (no extra dependency). The GitHub API is unauthenticated
(60 requests/hour/IP) which is plenty for a local, user-triggered check.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.core.config import settings
from app.models.media import VersionInfo


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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            message = "Límite de la API de GitHub alcanzado; inténtalo más tarde."
        elif exc.code == 404:
            message = "No hay releases públicas (¿el repositorio es privado?)."
        else:
            message = f"GitHub respondió con un error ({exc.code})."
        return VersionInfo(current=current, error=message)
    except (urllib.error.URLError, TimeoutError, OSError):
        return VersionInfo(
            current=current, error="No se pudo comprobar (¿sin conexión?)."
        )
    except (ValueError, json.JSONDecodeError):
        return VersionInfo(current=current, error="Respuesta inesperada de GitHub.")

    latest = data.get("tag_name")
    if not isinstance(latest, str):
        return VersionInfo(current=current, error="No hay releases publicadas todavía.")

    release_url = data.get("html_url")
    return VersionInfo(
        current=current,
        latest=latest,
        update_available=_is_newer(latest, current),
        release_url=release_url if isinstance(release_url, str) else None,
    )
