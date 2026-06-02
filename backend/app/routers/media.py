"""`/api/thumbnail` — proxy remote thumbnails through the local backend.

Some source CDNs (notably Instagram's cdninstagram/fbcdn) block hotlinking of
their images from another origin, so a browser `<img src=remoteUrl>` fails.
Fetching the image server-side and re-serving it from localhost sidesteps that.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, HTTPException, Query, Response, status

router = APIRouter(tags=["media"])

# A desktop browser User-Agent: some CDNs reject obviously-automated clients.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT_SECONDS = 10.0
# Cache in the browser for a day; thumbnails are effectively immutable.
_CACHE_CONTROL = "public, max-age=86400"


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

    Validates the scheme (only http/https are allowed) as a basic SSRF guard,
    then re-serves the bytes with the upstream content type and a cache header.
    Any failure becomes a 4xx/5xx so the frontend's `onError` fallback runs.

    The optional ``referer`` is forwarded as the ``Referer`` header so
    hotlink-protected CDNs (which a browser ``<img>`` can't satisfy across
    origins) serve the image.
    """
    # The frontend url-encodes the value, but be tolerant of double-decoding.
    target = unquote(url)
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only http(s) thumbnail URLs are allowed.",
        )

    headers = {"User-Agent": _USER_AGENT}
    if referer:
        referer_value = unquote(referer)
        if urlparse(referer_value).scheme in ("http", "https"):
            headers["Referer"] = referer_value

    request = urllib.request.Request(  # noqa: S310 — scheme validated above
        target,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 — scheme validated above
            request, timeout=_TIMEOUT_SECONDS
        ) as upstream:
            data = upstream.read()
            content_type = upstream.headers.get_content_type() or "image/jpeg"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch the thumbnail: {exc}",
        ) from exc

    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": _CACHE_CONTROL},
    )
