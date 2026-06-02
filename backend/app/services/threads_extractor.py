"""Custom yt-dlp extractor for Threads (Meta).

yt-dlp ships no Threads extractor, and Threads only serves the media when the
request carries a real browser TLS fingerprint — a plain request gets a reduced
HTML with no video at all. We download the post page with ``curl_cffi``
impersonation (already a dependency for Cloudflare sites) and parse the embedded
Instagram-style media JSON (``video_versions`` / ``image_versions2`` /
``caption``).

It is registered on the ``YoutubeDL`` instances in ``ytdlp_service`` and
``download_service`` via ``add_info_extractor`` — it does NOT modify the bundled
yt-dlp package, so updating yt-dlp can never clobber it.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import ExtractorError, int_or_none, url_or_none


class ThreadsIE(InfoExtractor):
    """Resolve a single Threads post to its (Instagram-hosted) video."""

    IE_NAME = "threads"
    _VALID_URL = (
        r"https?://(?:www\.)?threads\.(?:net|com)/"
        r"(?:@(?P<user>[^/?#]+)/)?(?:post|t)/(?P<id>[\w-]+)"
    )

    @staticmethod
    def _json_array(key: str, text: str) -> list[dict[str, Any]] | None:
        """Parse the first ``"key":[ ... ]`` JSON array out of an HTML blob.

        The arrays we need (``video_versions``, image ``candidates``) hold flat
        objects with no nested brackets, so a non-``]`` run captures the whole
        array; ``json.loads`` then resolves the ``\\/`` and ``\\uXXXX`` escapes.
        """
        match = re.search(rf'"{key}":(\[[^\]]*\])', text)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(1))
        except ValueError:
            return None
        return parsed if isinstance(parsed, list) else None

    @classmethod
    def _thumbnail(cls, text: str) -> str | None:
        """Highest-res cover frame from a media ``image_versions2`` block.

        Anchored to ``image_versions2`` (not a bare ``candidates``) so it can't
        pick up an avatar thumbnail, and returns the LAST non-empty block in the
        text — Threads emits empty placeholder media (``candidates":[]``) before
        the real object, so the cover is the last one preceding the real video.
        """
        thumbnail: str | None = None
        for match in re.finditer(r'"image_versions2":\{"candidates":(\[[^\]]*\])', text):
            try:
                candidates = json.loads(match.group(1))
            except ValueError:
                continue
            usable = [c for c in candidates if isinstance(c, dict) and c.get("url")]
            if usable:
                best = max(usable, key=lambda c: c.get("height") or 0)
                thumbnail = url_or_none(best.get("url"))  # last non-empty wins
        return thumbnail

    @staticmethod
    def _caption(text: str) -> str | None:
        """Extract the post caption, decoding its JSON string escapes."""
        match = re.search(r'"caption":\{"text":"((?:[^"\\]|\\.)*)"', text)
        if not match:
            return None
        try:
            return json.loads(f'"{match.group(1)}"')
        except ValueError:
            return None

    @staticmethod
    def _efg_duration(video_url: str) -> int | None:
        """The signed URL embeds a base64 ``efg`` blob carrying ``duration_s``."""
        match = re.search(r"[?&]efg=([\w-]+)", video_url)
        if not match:
            return None
        token = match.group(1)
        try:
            decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            data = json.loads(decoded)
        except (binascii.Error, ValueError):
            return None
        return int_or_none(data.get("duration_s")) if isinstance(data, dict) else None

    def _real_extract(self, url: str) -> dict[str, Any]:
        mobj = self._match_valid_url(url)
        video_id = mobj.group("id")
        user = mobj.group("user")

        # Threads only returns the media to a genuine browser fingerprint.
        webpage = self._download_webpage(
            url,
            video_id,
            note="Downloading post page",
            impersonate=ImpersonateTarget("chrome"),
        )

        # Threads embeds empty *placeholder* media objects next to the real one
        # (``video_versions":null``, ``candidates":[]``), so anchoring on the
        # shortcode is unreliable. Anchor instead on the real media: the first
        # video_versions that is a non-empty array of objects.
        anchor = re.search(r'"video_versions":\[\{', webpage)
        versions = (
            self._json_array("video_versions", webpage[anchor.start():])
            if anchor
            else None
        )

        formats: list[dict[str, Any]] = []
        seen: set[str] = set()
        for version in versions or []:
            video_url = url_or_none(version.get("url"))
            if not video_url or video_url in seen:
                continue
            seen.add(video_url)
            formats.append(
                {
                    "url": video_url,
                    "format_id": str(version.get("type") or len(formats)),
                    "ext": "mp4",
                    "width": int_or_none(version.get("width")),
                    "height": int_or_none(version.get("height")),
                }
            )

        if not formats:
            raise ExtractorError(
                "No downloadable video found in this Threads post "
                "(it may be image-only, private, or removed).",
                expected=True,
            )

        # The cover frame sits in the same media object as video_versions, but
        # how far before it varies with caption length, so scan everything up to
        # the real video and take the closest non-empty image_versions2 (the
        # cover) via _thumbnail's last-wins. Fall back to og:image only as a last
        # resort — on Threads that is the uploader's avatar, not the cover.
        thumbnail = self._thumbnail(webpage[: anchor.start()]) or self._og_search_thumbnail(
            webpage, default=None
        )

        caption = self._caption(webpage)
        title = re.sub(r"\s+", " ", caption).strip() if caption else ""

        return {
            "id": video_id,
            "title": (title[:100] or f"Threads video {video_id}"),
            "description": caption or None,
            "uploader": user,
            "uploader_id": user,
            "thumbnail": thumbnail,
            "duration": self._efg_duration(formats[0]["url"]),
            "webpage_url": url,
            "formats": formats,
        }


def register(ydl: Any) -> None:
    """Register :class:`ThreadsIE` on a ``YoutubeDL`` instance.

    ``add_info_extractor`` appends to the extractor list, which puts us *after*
    the catch-all ``Generic`` extractor — and since ``Generic`` is "suitable"
    for every URL, it would win and fail with ``Unsupported URL`` before ours is
    ever tried. We re-insert ``Threads`` at the front so it takes precedence for
    ``threads.com``/``.net`` links (its ``_VALID_URL`` is specific, so it never
    shadows other sites).
    """
    ydl.add_info_extractor(ThreadsIE())
    ies = ydl._ies
    key = ThreadsIE.ie_key()
    if key in ies:
        ydl._ies = {key: ies.pop(key), **ies}
