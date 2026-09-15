"""Patched Odnoklassniki (ok.ru) extractor.

The bundled yt-dlp extractor calls ``_parse_json`` on ``flashvars['metadata']``,
but ok.ru now serves that field as an **already-parsed object** (a dict), so the
parse raises ``TypeError: the JSON object must be str, bytes or bytearray, not
dict`` and the whole extraction dies with an unhandled error.

This subclass makes ``_parse_json`` pass a dict straight through (string inputs —
like the player config — still parse normally), which is enough to fix the
extraction without patching the yt-dlp package. Registered ahead of the bundled
extractor via ``add_info_extractor`` (re-inserted at the front of ``_ies``), so a
yt-dlp update can never clobber it and it only affects this one host.
"""

from __future__ import annotations

from typing import Any

from yt_dlp.extractor.odnoklassniki import OdnoklassnikiIE


# ok.ru's progressive MP4s are labelled only by a quality *name*, with no height
# or codecs — map each name to its standard height so the app can offer real
# quality tiers (and yt-dlp's height<= selector can pick them).
_QUALITY_HEIGHTS = {
    "mobile": 144,
    "lowest": 240,
    "low": 360,
    "sd": 480,
    "hd": 720,
    "full": 1080,
    "quad": 1440,
    "ultra": 2160,
}


class PatchedOdnoklassnikiIE(OdnoklassnikiIE):
    """OdnoklassnikiIE with a dict-tolerant ``_parse_json`` and annotated formats."""

    IE_NAME = "odnoklassniki:patched"

    def _parse_json(self, json_string: Any, video_id: Any, *args: Any, **kwargs: Any) -> Any:
        # ok.ru now hands `flashvars.metadata` as an already-parsed dict; the
        # inherited _extract_desktop still calls _parse_json on it, which raises.
        # A dict is already the parsed result — return it unchanged. Everything
        # else (the player config, a string) parses through the normal path.
        if isinstance(json_string, dict):
            return json_string
        return super()._parse_json(json_string, video_id, *args, **kwargs)

    @staticmethod
    def _annotate_formats(formats: Any) -> None:
        """Give ok.ru's name-only progressive MP4s a height + codecs.

        Those formats arrive as ``{url, ext, format_id: <name>}`` — no height, no
        vcodec/acodec — so the app treats them as neither video nor audio and can't
        list them as quality choices. They're muxed H.264/AAC MP4s, so fill that
        in and map the quality name to a standard height (leaving the HLS variants,
        which already carry a resolution, untouched).
        """
        if not isinstance(formats, list):
            return
        for fmt in formats:
            if not isinstance(fmt, dict) or fmt.get("height"):
                continue
            height = _QUALITY_HEIGHTS.get(fmt.get("format_id"))
            if not height:
                continue
            fmt["height"] = height
            fmt["resolution"] = f"{height}p"
            if fmt.get("vcodec") in (None, "none"):
                fmt["vcodec"] = "h264"
            if fmt.get("acodec") in (None, "none"):
                fmt["acodec"] = "aac"

    def _real_extract(self, url: str) -> Any:
        info = super()._real_extract(url)
        if isinstance(info, dict):
            self._annotate_formats(info.get("formats"))
        return info


def register(ydl: Any) -> None:
    """Register :class:`PatchedOdnoklassnikiIE` ahead of the bundled extractor.

    ``add_info_extractor`` appends, which would leave the bundled (buggy)
    OdnoklassnikiIE to match first. Re-insert ours at the front of ``_ies`` so it
    wins for ok.ru URLs; it inherits the same ``_VALID_URL``, so it shadows only
    that host and nothing else.
    """
    ydl.add_info_extractor(PatchedOdnoklassnikiIE())
    ies = ydl._ies
    key = PatchedOdnoklassnikiIE.ie_key()
    if key in ies:
        ydl._ies = {key: ies.pop(key), **ies}
