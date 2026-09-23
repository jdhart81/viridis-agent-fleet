"""Tests for request_context.py — one per RC invariant (G6 transport side)."""
import asyncio
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from request_context import (RequestContextMiddleware, build_context,  # noqa: E402
                             classify_user_agent, current_request_context,
                             request_context)


def test_channel_classification_table():
    assert classify_user_agent("Smithery/1.0 proxy") == "smithery-proxy"
    assert classify_user_agent("Claude-Desktop/0.9") == "claude-desktop"
    assert classify_user_agent("claude-code/2.1") == "claude-client"
    assert classify_user_agent("ChatGPT-Connector") == "chatgpt"
    assert classify_user_agent("python-httpx/0.27") == "script"
    assert classify_user_agent("curl/8.5.0") == "script"
    assert classify_user_agent("Mozilla/5.0 (Macintosh)") == "browser"
    assert classify_user_agent("") == "unknown"
    assert classify_user_agent("weird-новый-client") == "other"


def test_RC2_internal_requires_exact_secret(monkeypatch):
    monkeypatch.setenv("VIRIDIS_INTERNAL_SECRET", "hush")
    ctx = build_context("curl/8", "hush:nightkeeper-selftest", "1.2.3.4")
    assert ctx == {"consumer_class": "internal", "channel": "internal",
                   "caller": "internal:nightkeeper-selftest", "is_test": True,
                   "x402_payment": None}
    # Wrong secret => external, never internal (spoof-proof), never an error.
    spoof = build_context("curl/8", "guess:nightkeeper-selftest", "1.2.3.4")
    assert spoof["consumer_class"] == "external"
    assert not (spoof["caller"] or "").startswith("internal:")
    # Unset env disables internal tagging entirely.
    monkeypatch.delenv("VIRIDIS_INTERNAL_SECRET")
    off = build_context("curl/8", "hush:nightkeeper-selftest", "1.2.3.4")
    assert off["consumer_class"] == "external"


def test_RC4_fingerprint_leaks_no_raw_identifiers(monkeypatch):
    monkeypatch.delenv("VIRIDIS_INTERNAL_SECRET", raising=False)
    ctx = build_context("curl/8.5.0", None, "203.0.113.99")
    assert ctx["consumer_class"] == "external"
    assert ctx["caller"].startswith("ext:") and len(ctx["caller"]) == 16
    assert "203.0.113.99" not in ctx["caller"] and "curl" not in ctx["caller"]
    # Deterministic per client, distinct across clients.
    assert ctx == build_context("curl/8.5.0", None, "203.0.113.99")
    assert ctx["caller"] != build_context("curl/8.5.0", None, "203.0.113.98")["caller"]


def test_RC5_default_context_when_unbound():
    assert current_request_context() == {
        "consumer_class": "unknown", "channel": "unknown",
        "caller": None, "is_test": False, "x402_payment": None}
    with request_context({"consumer_class": "internal", "channel": "internal",
                          "caller": "internal:x", "is_test": True}):
        assert current_request_context()["consumer_class"] == "internal"
    assert current_request_context()["consumer_class"] == "unknown"


def test_RC1_middleware_binds_and_never_blocks(monkeypatch):
    monkeypatch.setenv("VIRIDIS_INTERNAL_SECRET", "hush")
    captured = {}

    async def inner_app(scope, receive, send):
        captured.update(current_request_context())

    mw = RequestContextMiddleware(inner_app)
    scope = {"type": "http", "client": ("10.0.0.7", 1234),
             "headers": [(b"user-agent", b"Smithery/2.0"),
                         (b"x-forwarded-for", b"198.51.100.4, 10.0.0.1")]}
    asyncio.run(mw(scope, None, None))
    assert captured["consumer_class"] == "external"
    assert captured["channel"] == "smithery-proxy"
    # XFF first hop (not the proxy-internal client addr) feeds the fingerprint.
    direct = {}

    async def inner2(scope, receive, send):
        direct.update(current_request_context())
    scope2 = {"type": "http", "client": ("10.0.0.7", 1234),
              "headers": [(b"user-agent", b"Smithery/2.0")]}
    asyncio.run(RequestContextMiddleware(inner2)(scope2, None, None))
    assert direct["caller"] != captured["caller"]
    # Non-http scopes and garbage headers still reach the app (deny-nothing).
    ok = {}

    async def inner3(scope, receive, send):
        ok["ran"] = True
    asyncio.run(RequestContextMiddleware(inner3)({"type": "lifespan"}, None, None))
    assert ok["ran"]
    asyncio.run(RequestContextMiddleware(inner3)(
        {"type": "http", "headers": [(b"x-viridis-internal", b"\xff\xfe")],
         "client": None}, None, None))


def test_RC1_internal_header_end_to_end(monkeypatch):
    monkeypatch.setenv("VIRIDIS_INTERNAL_SECRET", "hush")
    got = {}

    async def inner(scope, receive, send):
        got.update(current_request_context())
    scope = {"type": "http", "client": ("127.0.0.1", 9),
             "headers": [(b"user-agent", b"python-httpx/0.27"),
                         (b"x-viridis-internal", b"hush:nightkeeper-selftest")]}
    asyncio.run(RequestContextMiddleware(inner)(scope, None, None))
    assert got["caller"] == "internal:nightkeeper-selftest"
    assert got["is_test"] is True
