"""SSRF-safe HTTP fetching for user-influenced URLs.

Any endpoint that fetches a URL the client can influence (the thumbnail proxy's
`url`, the auto-tag `cover_url`) must not be turnable into a probe of internal
hosts. This module resolves the URL's host, rejects it if any address is
non-public, and connects to that exact validated IP — closing the
DNS-rebinding/TOCTOU window between the check and the connect — while keeping
SNI/cert validation against the real hostname and re-validating on every
redirect hop. Shared so both callers get identical guarantees.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

# Cap any read so a huge/streaming response can't exhaust local memory.
DEFAULT_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_TIMEOUT = 10.0


class SafeHTTPError(Exception):
    """A URL is disallowed (non-public/bad scheme) or couldn't be fetched safely."""


def ip_is_public(ip_str: str) -> bool:
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


def host_is_blocked(hostname: str | None) -> bool:
    """True if the host resolves to (or is) a non-public address.

    Public content lives on public hosts, so we reject loopback/private/
    link-local/reserved/multicast targets. This stops these endpoints from being
    abused for SSRF — e.g. a web page hitting `localhost:8756` to probe
    `127.0.0.1`, the cloud metadata endpoint, or other internal hosts. Blocks the
    host if *any* resolved address is non-public.
    """
    if not hostname:
        return True
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OSError):
        return True
    return not all(ip_is_public(info[4][0]) for info in infos)


def _resolve_pinned(host: str, port: int | None) -> list[Any]:
    """Resolve to validated public addrinfos, or [] if any is non-public/none."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    if not infos or not all(ip_is_public(info[4][0]) for info in infos):
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
        if parsed.scheme not in ("http", "https") or host_is_blocked(parsed.hostname):
            raise urllib.error.HTTPError(
                newurl, code, "Redirect to a disallowed host", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# A urllib opener wired with the pinned connections + redirect re-validation.
OPENER = urllib.request.build_opener(
    _PinnedHTTPHandler, _PinnedHTTPSHandler, _SafeRedirects
)


def fetch_public(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[bytes, str]:
    """Fetch a public http(s) URL safely; return ``(data, content_type)``.

    Raises :class:`SafeHTTPError` for a bad scheme, a non-public host, a fetch
    failure, or a response over ``max_bytes``. The connection is pinned to the
    validated IP and the read is capped.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or host_is_blocked(parsed.hostname):
        raise SafeHTTPError("URL is not a public http(s) address")
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with OPENER.open(request, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
            content_type = resp.headers.get_content_type() or "application/octet-stream"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SafeHTTPError("could not fetch the URL") from exc
    if len(data) > max_bytes:
        raise SafeHTTPError("response exceeds the size limit")
    return data, content_type
