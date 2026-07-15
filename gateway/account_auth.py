"""Request-scoped bearer attribution for Viridis billing.

This is deliberately authentication-light: an absent, malformed, or unknown
bearer never blocks a request.  It only gives the payment gate an account key
to resolve against the subscription ledger.  Read surfaces remain open and the
existing anonymous freemium path remains the fail-safe default.

Raw account keys live only in a request-local ContextVar.  They are never
logged, copied into tool payloads, or returned by this module.
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import Iterator, Optional


_ACCOUNT_KEY = contextvars.ContextVar("viridis_account_key", default=None)


def current_account_key() -> Optional[str]:
    """Return the bearer token bound to the current request, if any."""
    value = _ACCOUNT_KEY.get()
    return value if isinstance(value, str) and value else None


def _parse_bearer(value: str | None) -> Optional[str]:
    if not isinstance(value, str):
        return None
    parts = value.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1]
    # Account keys are URL-safe opaque tokens.  Reject whitespace/control
    # characters and absurd inputs without turning auth into a deny gate.
    if not token or len(token) > 256 or any(ord(ch) < 33 for ch in token):
        return None
    return token


@contextlib.contextmanager
def account_key_context(account_key: str | None) -> Iterator[None]:
    """Bind a key for a local/test call without exposing it in the payload."""
    marker = _ACCOUNT_KEY.set(account_key if isinstance(account_key, str) else None)
    try:
        yield
    finally:
        _ACCOUNT_KEY.reset(marker)


class AccountContextMiddleware:
    """ASGI middleware that binds ``Authorization: Bearer`` per request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = None
        if scope.get("type") == "http":
            values = [raw_value for raw_name, raw_value in scope.get("headers", [])
                      if raw_name.lower() == b"authorization"]
            # Multiple Authorization headers are ambiguous and therefore
            # attribute nothing; the request continues anonymously.
            if len(values) == 1:
                try:
                    token = _parse_bearer(values[0].decode("latin-1"))
                except Exception:
                    token = None
        marker = _ACCOUNT_KEY.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            _ACCOUNT_KEY.reset(marker)
