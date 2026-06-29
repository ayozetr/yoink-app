"""Custom yt-dlp extractor for embedded-player video hosts.

Some sites only expose their real media URL through the JS player config
(``window.initials``), and the bundled yt-dlp extractor resolves a stale CDN host
that now answers ``403``. We fetch the page with ``curl_cffi`` impersonation
(already a dependency) and read the working source URLs straight from the player
config — the same ones the browser uses.

Registered on the ``YoutubeDL`` instances in ``ytdlp_service`` and
``download_service`` via ``add_info_extractor`` (re-inserted at the front so it
takes precedence over the bundled extractor), so it never patches the yt-dlp
package and an update can't clobber it.

Supported hosts are kept base64-encoded so the source stays neutral.
"""

from __future__ import annotations

import base64
import re
from typing import Any

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import ExtractorError, int_or_none

# Hosts this extractor takes over, encoded (so a plain-text/grep of the source
# stays neutral). Add more entries — same player structure works as-is.
_HOSTS = tuple(base64.b64decode(b).decode() for b in (b"eGhhbXN0ZXI=",))


def _balanced_object(text: str, marker: str) -> str | None:
    """Return the first balanced ``{...}`` object that follows ``marker``.

    A brace counter that ignores braces inside strings, so it survives the URLs
    and captions in the config without needing a greedy regex (which overshoots).
    """
    i = text.find(marker)
    if i < 0:
        return None
    start = text.find("{", i)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    return None


class EmbeddedVRIE(InfoExtractor):
    """Resolve a player-config page to its working direct media URLs."""

    IE_NAME = "embeddedvr"
    _HOST_RE = "|".join(re.escape(h) for h in _HOSTS)
    _VALID_URL = (
        r"https?://(?:[\w-]+\.)?(?:" + _HOST_RE + r")\.(?:com|desi)/"
        r"(?:[^/?#]+/)*(?P<id>[\w-]+)"
    )

    def _gather(
        self,
        node: Any,
        formats: list[dict[str, Any]],
        seen: set[str],
        referer: str,
        label: str | None = None,
    ) -> None:
        """Walk a ``sources`` subtree, collecting direct (http) mp4 URLs.

        Each quality is keyed either by its parent key (``"1920p"``) or a
        per-item ``quality`` field. Thumbnail teasers and encrypted (non-http)
        standard URLs are skipped.
        """
        if isinstance(node, dict):
            url = node.get("url")
            if (
                isinstance(url, str)
                and url.startswith("http")
                and ".mp4" in url
                and "thumb" not in url
                and url not in seen
            ):
                seen.add(url)
                quality = str(node.get("quality") or node.get("label") or label or "")
                formats.append(
                    {
                        "url": url,
                        "ext": "mp4",
                        "format_id": quality or str(len(formats)),
                        "height": int_or_none(re.sub(r"\D", "", quality)) or None,
                        "http_headers": {"Referer": referer},
                    }
                )
            for key, value in node.items():
                if key != "url":
                    self._gather(value, formats, seen, referer, str(key))
        elif isinstance(node, list):
            for value in node:
                self._gather(value, formats, seen, referer, label)

    @staticmethod
    def _vr_layout(vr_type: Any) -> str | None:
        """Map a player ``vr.type`` (e.g. ``STEREO_180_LR``) to a Yoink layout."""
        text = str(vr_type or "").upper()
        if not text:
            return None
        deg = "360" if "360" in text else "180"
        if "_TB" in text or "_OU" in text or "TOPBOTTOM" in text:
            stereo = "tb"
        elif "MONO" in text:
            stereo = "mono"
        else:  # LR / default
            stereo = "sbs"
        return f"{deg}_{stereo}"

    def _real_extract(self, url: str) -> dict[str, Any]:
        video_id = self._match_id(url)
        webpage = self._download_webpage(
            url,
            video_id,
            note="Downloading player page",
            impersonate=ImpersonateTarget("chrome"),
        )

        raw = _balanced_object(webpage, "window.initials")
        data = self._parse_json(raw, video_id, fatal=False) if raw else None
        if not isinstance(data, dict):
            raise ExtractorError("Couldn't read the player config.", expected=True)

        formats: list[dict[str, Any]] = []
        seen: set[str] = set()
        for container in (data.get("vr"), data.get("xplayerSettings")):
            sources = container.get("sources") if isinstance(container, dict) else None
            if sources:
                self._gather(sources, formats, seen, url)

        if not formats:
            raise ExtractorError(
                "No downloadable format in the player config — the video may use "
                "an encrypted, standard-only source.",
                expected=True,
            )

        model = data.get("videoModel") if isinstance(data.get("videoModel"), dict) else {}
        vr = data.get("vr") if isinstance(data.get("vr"), dict) else {}
        title = (
            model.get("title")
            or vr.get("title")
            or self._og_search_title(webpage, default=None)
            or video_id
        )
        result: dict[str, Any] = {
            "id": video_id,
            "title": re.sub(r"\s+", " ", str(title)).strip()[:120] or video_id,
            "thumbnail": self._og_search_thumbnail(webpage, default=None),
            "duration": int_or_none(model.get("duration")),
            "webpage_url": url,
            "formats": formats,
        }
        # The sources came from the player's VR block, so it *is* immersive — pass
        # the exact layout on so detect_vr seeds the preview's VR toggle correctly
        # instead of guessing from a (VR-free) title.
        layout = self._vr_layout(vr.get("type"))
        if layout:
            result["vr_layout_hint"] = layout
        return result


def register(ydl: Any) -> None:
    """Register :class:`EmbeddedVRIE` and move it ahead of the bundled extractors.

    ``add_info_extractor`` appends, which would leave the bundled host extractor
    (and the catch-all ``Generic``) to match first. Re-insert ours at the front
    of ``_ies`` so it wins for the hosts it supports; its ``_VALID_URL`` is
    host-specific, so it never shadows anything else.
    """
    ydl.add_info_extractor(EmbeddedVRIE())
    ies = ydl._ies
    key = EmbeddedVRIE.ie_key()
    if key in ies:
        ydl._ies = {key: ies.pop(key), **ies}
