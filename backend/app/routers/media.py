"""`/api/thumbnail` — proxy remote thumbnails through the local backend.

Some source CDNs (notably Instagram's cdninstagram/fbcdn) block hotlinking of
their images from another origin, so a browser `<img src=remoteUrl>` fails.
Fetching the image server-side and re-serving it from localhost sidesteps that.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.config import settings
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


def _ip_is_public(ip_str: str) -> bool:
    """True if a textual IP is a routable public address (not internal)."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _host_is_blocked(hostname: str | None) -> bool:
    """True if the host resolves to (or is) a non-public address.

    A thumbnail lives on a public CDN, so we reject loopback/private/link-local/
    reserved targets. This stops the proxy from being abused for SSRF — e.g. a
    web page open in the user's browser hitting `localhost:8756/api/thumbnail`
    to probe `127.0.0.1`, the cloud metadata endpoint, or other internal hosts.
    Blocks the host if *any* resolved address is non-public.
    """
    if not hostname:
        return True
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OSError):
        return True
    return not all(_ip_is_public(info[4][0]) for info in infos)


def _resolve_pinned(host: str, port: int | None) -> list[Any]:
    """Resolve to validated public addrinfos, or [] if any is non-public/none."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    if not infos or not all(_ip_is_public(info[4][0]) for info in infos):
        return []
    return infos


# Connections that resolve, re-validate, and connect to the validated IP in one
# step — closing the TOCTOU/DNS-rebinding window between the up-front host check
# and the actual socket connect (a host whose DNS flips to 127.0.0.1 mid-request
# can't slip through, because the address used to connect is the one validated).
class _PinnedHTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        infos = _resolve_pinned(self.host, self.port)
        if not infos:
            raise OSError("host resolves to a disallowed address")
        self.sock = socket.create_connection(
            infos[0][4][:2], self.timeout, self.source_address
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self) -> None:
        infos = _resolve_pinned(self.host, self.port)
        if not infos:
            raise OSError("host resolves to a disallowed address")
        sock = socket.create_connection(
            infos[0][4][:2], self.timeout, self.source_address
        )
        # Keep SNI/cert validation against the real hostname, not the IP.
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req: urllib.request.Request) -> Any:
        return self.do_open(_PinnedHTTPConnection, req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req: urllib.request.Request) -> Any:
        return self.do_open(_PinnedHTTPSConnection, req)


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    """Re-validate scheme + host on every redirect hop.

    urllib only checks the initial URL, so a public URL that 302-redirects to an
    internal address would otherwise defeat the up-front guard. (The pinned
    connections re-validate at connect time too; this rejects early with a clear
    error and blocks non-http schemes.)
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


_opener = urllib.request.build_opener(
    _PinnedHTTPHandler, _PinnedHTTPSHandler, _SafeRedirects
)


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
