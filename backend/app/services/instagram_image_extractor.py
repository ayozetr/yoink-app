# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ayoze Torres

"""Patched Instagram extractors that surface **photo** items as downloadable.

yt-dlp's Instagram extractors build a media item's ``formats`` only from
``video_versions``; a photo's image (``image_versions2.candidates``) is kept as a
*thumbnail*, never a format. So a photo post downloads nothing, and
``InstagramStoryIE`` drops photo stories/highlights entirely (it keeps only items
that ``got formats``). The image URL *is* right there in the candidates, so these
subclasses promote the best candidate to a real image format (a ``.jpg``), which
makes photos download through the normal path and keeps photo items in a
highlight listing.

Both the single-post (``InstagramIE``) and story/highlight (``InstagramStoryIE``)
extractors run media through ``InstagramBaseIE._extract_product_media``, so each
subclass overrides just that one method. Registered ahead of the bundled
extractors via ``add_info_extractor`` (re-inserted at the front of ``_ies``), so a
yt-dlp update can't clobber them and they only affect instagram.com.
"""

from __future__ import annotations

from typing import Any

from yt_dlp.extractor.instagram import InstagramIE, InstagramStoryIE
from yt_dlp.utils import int_or_none, traverse_obj, url_or_none


def _is_image_only(info: dict[str, Any]) -> bool:
    """True when a resolved media item's only format is the promoted image."""
    formats = info.get("formats")
    return (
        isinstance(formats, list)
        and len(formats) == 1
        and formats[0].get("format_id") == "image"
    )


def _relabel_photo(info: dict[str, Any]) -> None:
    """yt-dlp titles every Instagram item ``Video by <user>``; for a photo that's
    misleading, so rename the default to ``Photo by <user>`` (a real caption title
    is left untouched). Recurses into a carousel's entries."""
    for entry in info.get("entries") or []:
        if isinstance(entry, dict):
            _relabel_photo(entry)
    if _is_image_only(info):
        title = info.get("title")
        if isinstance(title, str) and title.startswith("Video by "):
            info["title"] = "Photo by " + title[len("Video by "):]


def _promote_image(info: dict[str, Any], product_media: dict[str, Any]) -> dict[str, Any]:
    """If a media item has no video formats, add one from its best image candidate.

    ``image_versions2.candidates`` is ordered largest-first, so the first with a
    usable URL is the highest resolution. The format is marked image-only
    (``vcodec``/``acodec`` ``none``, ``ext`` jpg) so the backend can recognise it
    as a photo and download it directly — no merge, container or ffmpeg step.
    """
    if info.get("formats"):
        return info
    best = traverse_obj(
        product_media,
        (
            "image_versions2",
            "candidates",
            lambda _, v: url_or_none(v["url"]),
            any,
        ),
    )
    if not best:
        return info
    info["formats"] = [
        {
            "url": best["url"],
            "format_id": "image",
            "ext": "jpg",
            "width": int_or_none(best.get("width")),
            "height": int_or_none(best.get("height")),
            "vcodec": "none",
            "acodec": "none",
        }
    ]
    return info


class PatchedInstagramIE(InstagramIE):  # type: ignore[misc]
    """InstagramIE that also downloads photo posts (and photos in a carousel)."""

    IE_NAME = "instagram:patched"

    def _extract_product_media(self, product_media: Any) -> Any:
        info = super()._extract_product_media(product_media)
        if isinstance(info, dict) and isinstance(product_media, dict):
            return _promote_image(info, product_media)
        return info

    def _extract_product(self, product_info: Any, *args: Any, **kwargs: Any) -> Any:
        result = super()._extract_product(product_info, *args, **kwargs)
        if isinstance(result, dict):
            _relabel_photo(result)
        return result


class PatchedInstagramStoryIE(InstagramStoryIE):  # type: ignore[misc]
    """InstagramStoryIE that keeps photo stories/highlights (not just videos)."""

    IE_NAME = "instagram:story:patched"

    def _extract_product_media(self, product_media: Any) -> Any:
        info = super()._extract_product_media(product_media)
        if isinstance(info, dict) and isinstance(product_media, dict):
            return _promote_image(info, product_media)
        return info

    def _extract_product(self, product_info: Any, *args: Any, **kwargs: Any) -> Any:
        result = super()._extract_product(product_info, *args, **kwargs)
        if isinstance(result, dict):
            _relabel_photo(result)
        return result


def register(ydl: Any) -> None:
    """Register the patched Instagram extractors ahead of the bundled ones.

    ``add_info_extractor`` appends, which would leave the bundled extractors to
    match first. Re-insert ours at the front of ``_ies`` so they win for
    instagram.com URLs; they inherit the same ``_VALID_URL``, so they shadow only
    Instagram and nothing else.
    """
    for ie_cls in (PatchedInstagramStoryIE, PatchedInstagramIE):
        ydl.add_info_extractor(ie_cls())
        ies = ydl._ies
        key = ie_cls.ie_key()
        if key in ies:
            ydl._ies = {key: ies.pop(key), **ies}
