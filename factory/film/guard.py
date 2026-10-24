"""The request guard (AC-3, AC-4) and the loopback rule for the base URL.

Domain: no I/O. The page adapter aborts any request `blocked_label` names; the doubles use the
same function, so the rule has one source.
"""

import re
from urllib.parse import urlsplit

_SIX: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^/api/agents/[^/]+/gate$"), "gate run"),
    (re.compile(r"^/api/agents/[^/]+/coach/run$"), "coach run"),
    (re.compile(r"^/api/agents/[^/]+/scenarios/[^/]+/check$"), "single-scenario check"),
    (re.compile(r"^/api/brief$"), "brief proposal"),
    (re.compile(r"^/api/proposals/[^/]+/save$"), "proposal save"),
    (re.compile(r"^/api/avatar/session$"), "avatar session"),
)
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


class RunRefused(Exception):
    """A run or one of its checks is refused before any live session opens."""


def blocked_label(method: str, url: str) -> str | None:
    """The label of a request that starts a run, or None. Only POST starts one; every GET of
    the same path (reads) passes."""
    if method.upper() != "POST":
        return None
    path = urlsplit(url).path
    path = path.rstrip("/") or "/"
    for pattern, label in _SIX:
        if pattern.match(path):
            return label
    return None


def check_base_url(base_url: str) -> str:
    """The recorder talks to a demo server on this machine only (127.0.0.1, localhost, ::1)."""
    try:
        parts = urlsplit(base_url)
        host = parts.hostname
    except ValueError as exc:
        raise RunRefused(f"base URL is not a URL: {exc}") from exc
    if parts.scheme not in ("http", "https") or host not in LOOPBACK_HOSTS:
        raise RunRefused(
            f"base URL must be http(s) on loopback ({', '.join(LOOPBACK_HOSTS)}), got host {host!r}"
        )
    return base_url.rstrip("/")
