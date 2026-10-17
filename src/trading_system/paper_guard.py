"""Two independent guards that keep this system on PAPER trading only.

Guard 1 — ``validate_paper_endpoint``
    Parses the URL and requires ``scheme == https`` and
    ``hostname == paper-api.alpaca.markets`` EXACTLY, with no userinfo, no
    port override and no credentials embedded.

    A substring check is not enough.  ``https://evil.test/paper-api.alpaca.markets``
    contains the string "paper-api.alpaca.markets" but routes every order to
    an attacker's server.  So does
    ``https://paper-api.alpaca.markets.evil.test`` and
    ``https://paper-api.alpaca.markets@evil.test``.  All three are rejected
    here and all three are covered in ``tests/test_paper_guard.py``.

Guard 2 — ``assert_paper_mode``
    An independent check performed immediately before every order submission.
    It re-parses the URL that is actually about to be used (not the one that
    was validated at construction time) and additionally refuses if the
    process has live trading flagged on.  The two guards share no state, so a
    mistake in one does not disable the other.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlsplit

__all__ = [
    "PaperTradingViolation",
    "PAPER_HOST",
    "ALLOWED_PAPER_URLS",
    "validate_paper_endpoint",
    "assert_paper_mode",
    "is_paper_endpoint",
]


class PaperTradingViolation(RuntimeError):
    """Raised when anything would route an order off the paper endpoint."""


#: The one and only trading host this system will talk to.
PAPER_HOST = "paper-api.alpaca.markets"

#: Guard 2's independent allowlist.  Deliberately a separate constant from the
#: hostname comparison in guard 1 so the two do not share a single point of
#: failure.
ALLOWED_PAPER_URLS = frozenset(
    {
        "https://paper-api.alpaca.markets",
        "https://paper-api.alpaca.markets/",
    }
)

#: Host that would mean REAL money.  Named explicitly so the error message can
#: be unambiguous rather than a generic "bad URL".
LIVE_HOST = "api.alpaca.markets"


def validate_paper_endpoint(url: str) -> str:
    """Guard 1.  Return the normalised paper URL or raise.

    The comparison is on the PARSED HOSTNAME, never on a substring of the URL.
    """
    if url is None:
        raise PaperTradingViolation("Alpaca base URL is not set")
    cleaned = str(url).strip()
    if not cleaned:
        raise PaperTradingViolation("Alpaca base URL is empty")

    parts = urlparse(cleaned)

    if parts.scheme.lower() != "https":
        raise PaperTradingViolation(
            f"Alpaca base URL must use https, got scheme {parts.scheme!r} in {cleaned!r}"
        )

    # urlparse puts anything before '@' into username/password.  A URL like
    # https://paper-api.alpaca.markets@evil.test has hostname 'evil.test'.
    if parts.username or parts.password or "@" in (parts.netloc or ""):
        raise PaperTradingViolation(
            f"Alpaca base URL must not embed credentials: {cleaned!r}"
        )

    host = (parts.hostname or "").lower().rstrip(".")
    if host == LIVE_HOST:
        raise PaperTradingViolation(
            "Refusing to use the LIVE Alpaca endpoint. This system is paper-only. "
            f"Set ALPACA_BASE_URL=https://{PAPER_HOST}"
        )
    if host != PAPER_HOST:
        raise PaperTradingViolation(
            f"Alpaca base URL host must be exactly {PAPER_HOST!r}, got {host!r} "
            f"(from {cleaned!r}). A URL that merely CONTAINS the paper hostname, "
            f"such as https://evil.test/{PAPER_HOST}, is rejected on purpose."
        )

    if parts.port not in (None, 443):
        raise PaperTradingViolation(
            f"Alpaca base URL must use the default https port, got port {parts.port}"
        )

    # Only '' or '/' are acceptable paths for a base URL; anything else means
    # the real host is somewhere other than where it appears to be.
    path = (parts.path or "").rstrip("/")
    if path:
        raise PaperTradingViolation(
            f"Alpaca base URL must have no path component, got {parts.path!r}"
        )
    if parts.query or parts.fragment:
        raise PaperTradingViolation(
            f"Alpaca base URL must have no query or fragment: {cleaned!r}"
        )

    return f"https://{PAPER_HOST}"


def is_paper_endpoint(url: str) -> bool:
    """Non-raising form of guard 1."""
    try:
        validate_paper_endpoint(url)
    except PaperTradingViolation:
        return False
    return True


def assert_paper_mode(request_url: str, *, allow_live_env: str = "ALLOW_LIVE_TRADING") -> None:
    """Guard 2.  Called immediately before every order submission.

    Re-derives the base of the URL that is ACTUALLY about to be requested and
    checks it against an independent allowlist, then refuses outright if the
    process has live trading flagged on.
    """
    if os.environ.get(allow_live_env, "").strip().lower() in {"1", "true", "yes", "on"}:
        raise PaperTradingViolation(
            f"{allow_live_env} is set. This system does not support live trading; "
            "unset it and use the Alpaca paper account."
        )

    parts = urlsplit(str(request_url or "").strip())
    if parts.username or parts.password or "@" in (parts.netloc or ""):
        raise PaperTradingViolation(f"order URL embeds credentials: {request_url!r}")
    base = f"{parts.scheme.lower()}://{(parts.hostname or '').lower()}"
    if parts.port not in (None, 443):
        raise PaperTradingViolation(
            f"order URL must use the default https port: {request_url!r}"
        )
    if base not in ALLOWED_PAPER_URLS:
        raise PaperTradingViolation(
            f"Order blocked by the paper-trading guard: {base!r} is not an allowed "
            f"paper endpoint (allowed: {sorted(ALLOWED_PAPER_URLS)}). "
            f"Full URL was {request_url!r}."
        )
