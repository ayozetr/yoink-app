"""`/api/thumbnail` — proxy remote thumbnails through the local backend.

Some source CDNs (notably Instagram's cdninstagram/fbcdn) block hotlinking of
their images from another origin, so a browser `<img src=remoteUrl>` fails.
Fetching the image server-side and re-serving it from localhost sidesteps that.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from typing import Any
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
# Cap the upstream read so a huge/streaming response can't exhaust local memory.
_MAX_BYTES = 16 * 1024 * 1024  # 16 MB — generous for any real thumbnail


def _host_is_blocked(hostname: str | None) -> bool:
    """True if the host resolves to (or is) a non-public address.

    A thumbnail lives on a public CDN, so we reject loopback/private/link-local/
    reserved targets. This stops the proxy from being abused for SSRF — e.g. a
    web page open in the user's browser hitting `localhost:8756/api/thumbnail`
    to probe `127.0.0.1`, the cloud metadata endpoint, or other internal hosts.
    """
    if not hostname:
        return True
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OSError):
        return True
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    """Re-validate scheme + host on every redirect hop.

    urllib only checks the initial URL, so a public URL that 302-redirects to an
    internal address would otherwise defeat the up-front guard.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        parsed = urlparse(newurl)
        if parsed.scheme not in ("http", "https") or _host_is_blocked(parsed.hostname):
            raise urllib.error.HTTPError(
                newurl, code, "Redirect to a disallowed host", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirects())


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
    if parsed.scheme not in ("http", "https") or _host_is_blocked(parsed.hostname):
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
        with _opener.open(request, timeout=_TIMEOUT_SECONDS) as upstream:
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
