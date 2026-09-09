"""In-process broker between the backend and the app's WebView for PO-token minting.

The backend can't run YouTube's BotGuard JavaScript; the app's WebView can (it's
a real DOM/JS runtime). So when a download needs a per-video PO token, the
backend *submits a mint job* here and blocks (with a timeout) on the download
worker thread; the WebView — running a background loop that long-polls the
`/api/po-token/*` endpoints — picks the job up, mints the token with `bgutils-js`
(its network proxied back through the backend so the WebView never leaves
`127.0.0.1`), and posts the result, which unblocks the waiter.

If no WebView is polling (the headless CLI, or before the minter has started),
`submit_mint` simply times out and returns ``None`` — callers fall back to the
manual token. Everything here is thread-safe: the producer is a worker thread,
the consumer an HTTP handler on FastAPI's threadpool.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# How long the poller is parked waiting for a job before returning empty (so the
# WebView can re-issue its long-poll). Comfortably under a proxy/idle timeout.
_POLL_WAIT_SECONDS = 25.0

# A WebView is considered "present" if it long-polled within this window. Used to
# skip the mint (and its timeout) entirely on the headless CLI, where nothing polls.
_POLLER_FRESH_SECONDS = 60.0


@dataclass
class _Job:
    id: str
    video_id: str
    created_at: float
    done: threading.Event = field(default_factory=threading.Event)
    token: str | None = None
    dispatched: bool = False


class _Broker:
    """Thread-safe queue of mint jobs awaiting the WebView, plus their results."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._new_job = threading.Condition(self._lock)
        self._jobs: dict[str, _Job] = {}
        self._last_poll: float = 0.0  # monotonic time the WebView last long-polled

    def has_active_poller(self) -> bool:
        """True if the WebView long-polled recently — i.e. minting can be attempted
        (otherwise, e.g. on the headless CLI, don't submit and block for nothing)."""
        with self._lock:
            return time.monotonic() - self._last_poll < _POLLER_FRESH_SECONDS

    def submit_mint(self, video_id: str, timeout: float) -> str | None:
        """Enqueue a mint job and block until the WebView fulfills it or timeout.

        Returns the minted token, or ``None`` if no WebView answered in time.
        """
        job = _Job(id=uuid.uuid4().hex, video_id=video_id, created_at=time.monotonic())
        with self._lock:
            self._jobs[job.id] = job
            self._new_job.notify()  # wake a parked poller
        got = job.done.wait(timeout)
        with self._lock:
            self._jobs.pop(job.id, None)
        if not got:
            return None
        return job.token

    def next_job(self, wait: float = _POLL_WAIT_SECONDS) -> dict[str, str] | None:
        """Claim the oldest undispatched job for the WebView (long-poll).

        Blocks up to ``wait`` seconds for one to appear; returns ``{id, video_id}``
        or ``None`` when there's nothing to mint. A claimed job is marked
        dispatched so a second poller doesn't grab it too.
        """
        deadline = time.monotonic() + wait
        with self._lock:
            self._last_poll = time.monotonic()  # a WebView is here and asking
            while True:
                pending = sorted(
                    (j for j in self._jobs.values() if not j.dispatched),
                    key=lambda j: j.created_at,
                )
                if pending:
                    job = pending[0]
                    job.dispatched = True
                    return {"id": job.id, "video_id": job.video_id}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._new_job.wait(remaining)

    def complete(self, job_id: str, token: str | None) -> bool:
        """Deliver the WebView's result (a token, or ``None`` on failure).

        Returns True if the job was still waiting, False if it had already timed
        out / been claimed by nobody (a late result is harmlessly dropped).
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.token = token or None
            job.done.set()
            return True

    def _reset(self) -> None:
        """Drop all jobs — for tests."""
        with self._lock:
            for job in self._jobs.values():
                job.done.set()
            self._jobs.clear()


# Process-wide singleton.
broker = _Broker()
