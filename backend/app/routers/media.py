"""`/api/thumbnail` — proxy remote thumbnails through the local backend.

Some source CDNs (notably Instagram's cdninstagram/fbcdn) block hotlinking of
their images from another origin, so a browser `<img src=remoteUrl>` fails.
Fetching the image server-side and re-serving it from localhost sidesteps that.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.config import settings
from app.core.safe_http import OPENER, host_is_blocked
from app.services.autotag_service import extract_cover

router = APIRouter(tags=["media"])

# A desktop browser User-Agent: some CDNs reject obviously-automated clients.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT_SECONDS = 10.0
# Cache in the browser for a day; thumbnails are effectively immutable.
_CACHE_CONTROL = "public, max-age=86400"
# Cap the upstream read so a huge/streaming response can't exhaust local memory.
_MAX_BYTES = 16 * 1024 * 1024  # 16 MB — generous for any real thumbnail


@router.get(
    "/thumbnail",
    summary="Proxy a remote thumbnail image through the backend",
    responses={
        200: {"content": {"image/*": {}}},
        400: {"description": "Invalid or disallowed URL"},
        502: {"description": "Upstream image could not be fetched"},
    },
)
def proxy_thumbnail(
    url: str = Query(..., description="The remote image URL (url-encoded)."),
    referer: str | None = Query(
        default=None,
        description="Referer to forward (url-encoded). Some CDNs hotlink-protect "
        "their thumbnails and return 403 unless the request carries a Referer "
        "from the original page.",
    ),
) -> Response:
    """Fetch a remote image server-side and stream it back.

    Validates the scheme and the resolved host (http/https on a public address
    only) as an SSRF guard — re-checked on every redirect — and caps the read
    size. Any failure becomes a 4xx/5xx so the frontend's `onError` fallback runs.
    """
    # The frontend url-encodes the value, but be tolerant of double-decoding.
    target = unquote(url)
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https") or host_is_blocked(parsed.hostname):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only public http(s) thumbnail URLs are allowed.",
        )

    headers = {"User-Agent": _USER_AGENT}
    if referer:
        referer_value = unquote(referer)
        if urlparse(referer_value).scheme in ("http", "https"):
            headers["Referer"] = referer_value

    request = urllib.request.Request(  # noqa: S310 — scheme + host validated above
        target,
        headers=headers,
    )
    try:
        with OPENER.open(request, timeout=_TIMEOUT_SECONDS) as upstream:
            # Read one byte over the cap so we can tell "exactly at limit" from
            # "over"; a streaming/huge body can't balloon memory past this.
            data = upstream.read(_MAX_BYTES + 1)
            content_type = upstream.headers.get_content_type() or "image/jpeg"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # Don't echo the exception — its connect/timeout detail is an SSRF oracle.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not fetch the thumbnail.",
        ) from exc

    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Thumbnail exceeds the size limit.",
        )

    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": _CACHE_CONTROL},
    )


@router.get("/cover", summary="Embedded cover art of a downloaded audio file")
def get_cover(
    path: str = Query(..., description="Path to a file inside the download dir."),
) -> Response:
    """Serve the cover art embedded in a downloaded file (404 if none).

    The path is constrained to the download directory so the endpoint can't read
    arbitrary files on disk.
    """
    download_dir = settings.ensure_download_dir().resolve()
    target = Path(path).resolve()
    if target != download_dir and download_dir not in target.parents:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path is outside the download directory.",
        )
    if not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
        )
    cover = extract_cover(target)
    if cover is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No cover art."
        )
    data, mime = cover
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )
