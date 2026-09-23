#!/usr/bin/env python3
"""Recover MCP initialize when the SDK emits HTTP 200 without a message.

The MCP SDK's SSE response path sends HTTP 200 headers before the server has
produced the JSON-RPC response. If that response task fails, a caller can see
``200`` with an empty body. This middleware buffers initialize responses and,
only when the downstream response is missing/unparseable or times out, returns
a canonical stateless initialize result. Tool calls still execute through the
real mounted server.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any, Optional

_lock = threading.Lock()
_recoveries = 0
_last_reason: Optional[str] = None


def _timeout_seconds() -> float:
    raw = os.environ.get("MCP_INITIALIZE_TIMEOUT_SECONDS", "10")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 10.0
    return min(30.0, max(1.0, value))


def _parse_message(body: bytes) -> Optional[dict]:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    candidates = [text]
    candidates.extend(
        line[5:].strip() for line in text.splitlines()
        if line.startswith("data:"))
    for candidate in reversed(candidates):
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if (isinstance(parsed, dict) and parsed.get("jsonrpc") == "2.0"
                and ("result" in parsed or "error" in parsed)):
            return parsed
    return None


def status() -> dict:
    with _lock:
        return {
            "fallback_recoveries": _recoveries,
            "last_recovery_reason": _last_reason,
            "timeout_seconds": _timeout_seconds(),
        }


def _record(reason: str) -> None:
    global _recoveries, _last_reason
    with _lock:
        _recoveries += 1
        _last_reason = reason


def _fallback(payload: dict) -> bytes:
    params = payload.get("params")
    requested = (
        params.get("protocolVersion")
        if isinstance(params, dict) else None)
    protocol = (
        requested if isinstance(requested, str) and 1 <= len(requested) <= 32
        else "2025-03-26")
    return json.dumps({
        "jsonrpc": "2.0",
        "id": payload.get("id"),
        "result": {
            "protocolVersion": protocol,
            "capabilities": {
                "tools": {"listChanged": False},
                "prompts": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": "viridis-agent-stable",
                "version": "initialize-recovery-v1",
            },
            "instructions": (
                "Stateless Viridis fleet gateway. Call tools/list or tools/call "
                "on this same mount."),
        },
    }, separators=(",", ":")).encode()


class MCPInitializeRecoveryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope.get("type") != "http" or scope.get("method") != "POST"
                or not str(scope.get("path", "")).endswith("/mcp")):
            await self.app(scope, receive, send)
            return
        chunks = []
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        try:
            payload: Any = json.loads(body)
        except (UnicodeDecodeError, ValueError):
            payload = None
        if not isinstance(payload, dict) or payload.get("method") != "initialize":
            delivered = False

            async def replay_receive():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": body,
                        "more_body": False}

            await self.app(scope, replay_receive, send)
            return

        captured = []
        delivered = False

        async def replay_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def capture(message):
            captured.append(message)

        reason = None
        try:
            await asyncio.wait_for(
                self.app(scope, replay_receive, capture),
                timeout=_timeout_seconds())
        except asyncio.TimeoutError:
            reason = "downstream_timeout"
        except Exception:
            reason = "downstream_exception"

        start = next(
            (item for item in captured
             if item.get("type") == "http.response.start"), None)
        response_body = b"".join(
            item.get("body", b"") for item in captured
            if item.get("type") == "http.response.body")
        status_code = start.get("status") if start else None
        if reason is None and status_code == 200 \
                and _parse_message(response_body) is None:
            reason = "http_200_unparseable_body"
        if reason is None:
            for message in captured:
                await send(message)
            return

        _record(reason)
        encoded = _fallback(payload)
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(encoded)).encode()),
                (b"cache-control", b"no-store"),
                (b"x-viridis-initialize-recovered", b"1"),
            ],
        })
        await send({"type": "http.response.body", "body": encoded})
