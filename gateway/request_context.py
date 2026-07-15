"""Request-scoped caller classification for Viridis usage statistics (G6).

Mirrors account_auth.py: an ASGI middleware binds transport evidence
(User-Agent, X-Viridis-Internal, client address) into a request-local
ContextVar; the payment gate reads it when it meters a call. Classification
is derived SERVER-SIDE — nothing here is accepted from tool payloads, so a
public caller cannot spoof internal traffic.

Classification rules:
- ``X-Viridis-Internal: <secret>:<caller-name>`` where <secret> equals the
  VIRIDIS_INTERNAL_SECRET env (constant-time compare) =>
  consumer_class="internal", caller="internal:<caller-name>", is_test=True.
  Wrong/absent secret => header ignored (never an error; deny-nothing, like
  account_auth). If the env is unset, internal tagging is disabled entirely.
- Otherwise consumer_class="external"; channel derived from the User-Agent
  via CHANNEL_PATTERNS; caller is a privacy-safe fingerprint
  ``ext:<sha256(ip|ua)[:12]>`` — stable per client, reversible by nobody.
- No HTTP context at all (in-process calls, unit tests) => the module
  default: consumer_class="unknown", channel="unknown", caller=None.

--- INVARIANTS ---
RC1  Deny-nothing: no header state ever blocks or errors a request.
RC2  Spoof-proof internal: consumer_class="internal" requires the shared
     secret; a caller without it can only ever be external/unknown.
RC3  The raw secret is never logged, never echoed, never stored in events
     (only the derived caller name is).
RC4  Fingerprints contain no raw IP or UA — sha256 truncation only.
RC5  Absent context yields the safe default (unknown), never a crash.
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import hmac
import os
from typing import Iterator, Optional

_DEFAULT = {
    "consumer_class": "unknown",
    "channel": "unknown",
    "caller": None,
    "is_test": False,
}

_REQUEST_CONTEXT: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "viridis_request_context", default=None)

# Ordered User-Agent substring -> channel mapping (first match wins; all
# lowercase). Extend here as new client fingerprints appear in the wild.
CHANNEL_PATTERNS = (
    ("smithery", "smithery-proxy"),
    ("claude-desktop", "claude-desktop"),
    ("claude", "claude-client"),
    ("anthropic", "claude-client"),
    ("chatgpt", "chatgpt"),
    ("openai", "chatgpt"),
    ("mcp-inspector", "inspector"),
    ("glama", "registry-crawler"),
    ("pulsemcp", "registry-crawler"),
    ("modelcontextprotocol", "mcp-client"),
    ("mcp-remote", "mcp-client"),
    ("python-httpx", "script"),
    ("python-requests", "script"),
    ("python-urllib", "script"),
    ("aiohttp", "script"),
    ("curl", "script"),
    ("wget", "script"),
    ("node", "script"),
    ("go-http-client", "script"),
    ("mozilla", "browser"),
)

INTERNAL_HEADER = b"x-viridis-internal"
INTERNAL_SECRET_ENV = "VIRIDIS_INTERNAL_SECRET"


def classify_user_agent(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return "unknown"
    for needle, channel in CHANNEL_PATTERNS:
        if needle in ua:
            return channel
    return "other"


def _fingerprint(ip: str, user_agent: str) -> str:
    digest = hashlib.sha256(f"{ip}|{user_agent}".encode()).hexdigest()[:12]
    return f"ext:{digest}"


def _parse_internal(header_value: str) -> Optional[str]:
    """Validate the internal header. Returns the caller name, or None.
    Format: '<secret>:<caller-name>'. RC2/RC3."""
    secret = os.environ.get(INTERNAL_SECRET_ENV, "")
    if not secret or not isinstance(header_value, str) or ":" not in header_value:
        return None
    supplied, _, name = header_value.partition(":")
    if not hmac.compare_digest(supplied, secret):
        return None
    name = name.strip()[:64]
    return name or "unnamed"


def build_context(user_agent: str, internal_header: Optional[str],
                  client_ip: str) -> dict:
    internal_name = _parse_internal(internal_header) if internal_header else None
    if internal_name is not None:
        return {"consumer_class": "internal", "channel": "internal",
                "caller": f"internal:{internal_name}", "is_test": True}
    return {"consumer_class": "external",
            "channel": classify_user_agent(user_agent),
            "caller": _fingerprint(client_ip, user_agent),
            "is_test": False}


def current_request_context() -> dict:
    """The classification bound to the current request (RC5: safe default)."""
    value = _REQUEST_CONTEXT.get()
    return dict(value) if isinstance(value, dict) else dict(_DEFAULT)


@contextlib.contextmanager
def request_context(context: Optional[dict]) -> Iterator[None]:
    """Bind a context for a local/test call."""
    marker = _REQUEST_CONTEXT.set(context if isinstance(context, dict) else None)
    try:
        yield
    finally:
        _REQUEST_CONTEXT.reset(marker)


class RequestContextMiddleware:
    """ASGI middleware binding caller classification per request (RC1)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        context = None
        if scope.get("type") == "http":
            ua, internal = "", None
            for raw_name, raw_value in scope.get("headers", []):
                if raw_name == b"user-agent":
                    ua = raw_value.decode("latin-1", "replace")
                elif raw_name == INTERNAL_HEADER:
                    internal = raw_value.decode("latin-1", "replace")
            client = scope.get("client")
            # Honor the proxy chain's first hop when present (droplet sits
            # behind no proxy today; Smithery's proxy sets X-Forwarded-For).
            xff = next((v.decode("latin-1", "replace")
                        for n, v in scope.get("headers", [])
                        if n == b"x-forwarded-for"), None)
            ip = (xff.split(",")[0].strip() if xff
                  else (client[0] if client else "unknown"))
            try:
                context = build_context(ua, internal, ip)
            except Exception:   # RC1/RC5: classification never breaks a call
                context = None
        marker = _REQUEST_CONTEXT.set(context)
        try:
            await self.app(scope, receive, send)
        finally:
            _REQUEST_CONTEXT.reset(marker)
