"""Authenticated client for the internal Viridis Hub verification oracle.

The market process deliberately has no payment credential and never queries
Stripe, CDP, a wallet, or an RPC node.  It sends the already signed market
record to the gateway over the private Docker network.  The gateway owns the
existing payment state and returns a durable verification receipt.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.request
from typing import Any, Callable


class HubClientError(RuntimeError):
    pass


class HubVerificationClient:
    def __init__(self, url: str, secret: str, *,
                 opener: Callable[..., Any] = urllib.request.urlopen):
        self.url = str(url or "").strip()
        self.secret = str(secret or "")
        self.opener = opener
        if not self.url.startswith("http://gateway:"):
            raise HubClientError(
                "hub verifier must use the private gateway Docker hostname")
        if len(self.secret) < 32:
            raise HubClientError("hub event secret must be at least 32 characters")

    def verify(self, payload: dict) -> dict:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret.encode(), timestamp.encode() + b"." + body,
            hashlib.sha256).hexdigest()
        request = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Viridis-Hub-Timestamp": timestamp,
                "X-Viridis-Hub-Signature": signature,
                "User-Agent": "viridis-agent-market/1",
            })
        try:
            with self.opener(request, timeout=15) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read(1_000_000)
        except Exception as exc:
            raise HubClientError(
                f"hub verification unavailable: {type(exc).__name__}") from exc
        try:
            result = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise HubClientError("hub verifier returned non-JSON") from exc
        if status != 200 or not isinstance(result, dict):
            raise HubClientError(
                f"hub verifier refused settlement (HTTP {status})")
        if result.get("verified") is not True:
            reason = str(result.get("reason") or result.get("error") or
                         "settlement not independently verified")
            raise HubClientError(reason)
        return result


__all__ = ["HubClientError", "HubVerificationClient"]
