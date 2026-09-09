"""`/api/po-token/*` — the WebView side of PO-token minting.

The app's WebView runs a background loop that:
  1. long-polls ``GET /pending`` for a mint job (a video id the backend needs a
     token for),
  2. mints it with ``bgutils-js`` — whose network it routes through
     ``POST /proxy`` so the WebView itself never leaves ``127.0.0.1`` (no CSP
     relaxation, no second WebView window),
  3. posts the token back to ``POST /result``.

See ``docs/po-token-webview.md`` and ``services/po_token_bridge.py``.
"""

from __future__ import annotations

import base64
import logging
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.core.safe_http import OPENER, host_is_blocked
from app.services.po_token_bridge import broker

router = APIRouter(prefix="/po-token", tags=["po-token"])
logger = logging.getLogger(__name__)

# Only bgutils-js's own traffic (YouTube + Google's BotGuard attestation) may be
# proxied — this endpoint forwards a WebView-chosen request server-side, so it's
# scoped to Google-owned hosts to keep it from becoming a general open proxy.
_ALLOWED_SUFFIXES = (
    ".youtube.com",
    ".google.com",
    ".googleapis.com",
    ".gstatic.com",
    ".googlevideo.com",
    ".ytimg.com",
)
_PROXY_TIMEOUT = 15.0
_PROXY_MAX_BYTES = 4 * 1024 * 1024  # BotGuard payloads are small


class MintJob(BaseModel):
    """A pending mint job handed to the WebView."""

    id: str
    video_id: str


class MintResult(BaseModel):
    """The WebView's answer for a mint job (``token`` null on a mint failure)."""

    id: str
    token: str | None = None


class ProxyRequest(BaseModel):
    """A network request bgutils-js wants made on its behalf (base64 body)."""

    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body_b64: str | None = None


class ProxyResponse(BaseModel):
    status: int
    headers: dict[str, str]
    body_b64: str


@router.get("/pending", response_model=MintJob | None, summary="Next mint job (long-poll)")
def get_pending() -> Response | MintJob:
    """Long-poll for the next PO-token mint job; 204 when there's nothing to do."""
    job = broker.next_job()
    if job is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return MintJob(id=job["id"], video_id=job["video_id"])


@router.post("/result", summary="Deliver a minted token")
def post_result(result: MintResult) -> dict[str, bool]:
    """Fulfill a mint job with the token the WebView produced (or a failure)."""
    delivered = broker.complete(result.id, result.token)
    return {"ok": delivered}


def _proxy_host_allowed(host: str | None) -> bool:
    if not host:
        return False
    low = host.lower()
    return any(low == s[1:] or low.endswith(s) for s in _ALLOWED_SUFFIXES)


@router.post("/proxy", response_model=ProxyResponse, summary="Proxy bgutils-js network")
def post_proxy(req: ProxyRequest) -> ProxyResponse:
    """Forward one bgutils-js request to a Google host and return the response.

    Scoped to Google-owned hosts, http(s), a public address (SSRF-pinned via the
    shared opener), and a small size cap — so it can't be turned into a general
    proxy against arbitrary or internal services.
    """
    parsed = urlparse(req.url)
    if (
        parsed.scheme not in ("http", "https")
        or not _proxy_host_allowed(parsed.hostname)
        or host_is_blocked(parsed.hostname)
    ):
        raise HTTPException(status_code=400, detail="URL is not an allowed PO-token host.")

    data = base64.b64decode(req.body_b64) if req.body_b64 else None
    request = urllib.request.Request(  # noqa: S310 — scheme + host allowlisted above
        req.url,
        data=data,
        method=req.method.upper(),
        headers=req.headers,
    )
    try:
        with OPENER.open(request, timeout=_PROXY_TIMEOUT) as resp:
            body = resp.read(_PROXY_MAX_BYTES + 1)
            resp_headers = {
                k: v for k, v in resp.headers.items() if k.lower() == "content-type"
            }
            resp_status = resp.status
    except urllib.error.HTTPError as exc:
        # A non-2xx is a valid answer bgutils-js may need to see (e.g. a 401/403).
        body = exc.read(_PROXY_MAX_BYTES + 1) if exc.fp else b""
        resp_headers = {}
        resp_status = exc.code
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Upstream request failed.") from exc

    if len(body) > _PROXY_MAX_BYTES:
        raise HTTPException(status_code=502, detail="Upstream response too large.")

    return ProxyResponse(
        status=resp_status,
        headers=resp_headers,
        body_b64=base64.b64encode(body).decode("ascii"),
    )
