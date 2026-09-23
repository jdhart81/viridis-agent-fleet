#!/usr/bin/env python3
"""Fleet-wide HTTP request limits and finite-JSON enforcement.

The public Caddy edge owns the first 1 MB request-body cap.  This ASGI
middleware repeats the bound inside the gateway so a candidate container,
localhost smoke, or future proxy misconfiguration cannot bypass it.  JSON
numbers are also walked after parsing so exponent overflow such as ``1e999``
cannot become ``float('inf')`` inside any mounted agent.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

DEFAULT_MAX_BODY_BYTES = 1_000_000


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_non_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite(item) for item in value)
    return False


def _json_error(status: int, error_type: str, message: str) -> tuple:
    body = json.dumps({
        "status": "error",
        "error_type": error_type,
        "message": message,
    }, separators=(",", ":")).encode("utf-8")
    return (
        {"type": "http.response.start", "status": status,
         "headers": [(b"content-type", b"application/json"),
                     (b"content-length", str(len(body)).encode("ascii"))]},
        {"type": "http.response.body", "body": body},
    )


class RequestLimitsMiddleware:
    """Bound HTTP bodies and reject non-finite JSON before agent dispatch."""

    def __init__(self, app, max_body_bytes: int | None = None):
        configured = (
            os.environ.get("MAX_REQUEST_BODY_BYTES")
            if max_body_bytes is None else max_body_bytes
        )
        try:
            limit = int(configured) if configured is not None \
                else DEFAULT_MAX_BODY_BYTES
        except (TypeError, ValueError) as exc:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be an integer") from exc
        if limit < 1:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be positive")
        self.app = app
        self.max_body_bytes = limit

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
        }
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_bytes:
                    start, body = _json_error(
                        413, "request_body_too_large",
                        f"request body exceeds {self.max_body_bytes} bytes")
                    await send(start)
                    await send(body)
                    return
            except ValueError:
                start, body = _json_error(
                    400, "invalid_content_length",
                    "Content-Length must be an integer")
                await send(start)
                await send(body)
                return

        chunks = []
        size = 0
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_body_bytes:
                start, body = _json_error(
                    413, "request_body_too_large",
                    f"request body exceeds {self.max_body_bytes} bytes")
                await send(start)
                await send(body)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        raw_body = b"".join(chunks)
        content_type = headers.get(b"content-type", b"").decode(
            "latin-1", errors="ignore").lower()
        if raw_body and "json" in content_type:
            try:
                parsed = json.loads(
                    raw_body,
                    parse_constant=lambda token: (_ for _ in ()).throw(
                        ValueError(f"non-finite JSON constant: {token}")),
                )
            except UnicodeDecodeError:
                parsed = None  # downstream owns ordinary malformed JSON errors
            except json.JSONDecodeError:
                parsed = None
            except ValueError:
                start, body = _json_error(
                    400, "non_finite_number",
                    "JSON numbers must be finite")
                await send(start)
                await send(body)
                return
            if parsed is not None and _contains_non_finite(parsed):
                start, body = _json_error(
                    400, "non_finite_number",
                    "JSON numbers must be finite")
                await send(start)
                await send(body)
                return

        delivered = False

        async def replay_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": raw_body,
                        "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)


__all__ = [
    "DEFAULT_MAX_BODY_BYTES",
    "RequestLimitsMiddleware",
    "_contains_non_finite",
]
