#!/usr/bin/env python3
"""Unsigned MeshMCP Stage A verifier for the Viridis x402 boundary.

This probe has no signer, private-key, payment, or retry path. It sends one
fixed Regulatory Radar request, requires the live HTTP 402 contract to match
the expected Viridis route, and emits only the seller-side fields that a
MeshMCP audit record can correlate with its independently proved peer identity.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Callable


ENDPOINT = (
    "https://mcp.viridisconservation.com"
    "/x402/regulatory-radar/scan_regulations"
)
REQUEST = {
    "jurisdiction": "US",
    "sector": "energy",
    "query": "45V clean energy tax credit emissions disclosure",
}
REQUEST_BYTES = json.dumps(
    REQUEST, separators=(",", ":"), ensure_ascii=False).encode()
REQUEST_SHA256 = (
    "01d73e6bb71a94ed3366b41f81759ae0c7ad346be0fe68a2afa9cffd844a189b"
)
EXPECTED = {
    "x402_version": 2,
    "scheme": "exact",
    "network": "eip155:8453",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "pay_to": "0xfEf2e570b645EB720Ee6c589d27450810982f329",
    "quote_atomic_usdc": 10_000,
    "resource_url": ENDPOINT,
}
MAX_BODY_BYTES = 1_000_000


class StageAError(RuntimeError):
    pass


def _decode_payment_required(value: str) -> dict:
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4))
        result = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise StageAError("PAYMENT-REQUIRED is not valid base64 JSON") from exc
    if not isinstance(result, dict):
        raise StageAError("PAYMENT-REQUIRED must decode to an object")
    return result


def _fetch() -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(
        ENDPOINT,
        data=REQUEST_BYTES,
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "viridis-meshmcp-stage-a/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
            return response.status, dict(response.headers), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read(MAX_BODY_BYTES + 1)
        return exc.code, dict(exc.headers), raw


def probe(
        fetch: Callable[[], tuple[int, dict[str, str], bytes]] = _fetch
        ) -> dict[str, Any]:
    if hashlib.sha256(REQUEST_BYTES).hexdigest() != REQUEST_SHA256:
        raise StageAError("fixed request bytes no longer match request_sha256")
    status, headers, raw = fetch()
    if len(raw) > MAX_BODY_BYTES:
        raise StageAError("response body exceeds size cap")
    if status != 402:
        raise StageAError(f"expected HTTP 402, received {status}")
    normalized = {str(key).lower(): value for key, value in headers.items()}
    encoded = normalized.get("payment-required")
    if not encoded:
        raise StageAError("HTTP 402 omitted PAYMENT-REQUIRED")
    required = _decode_payment_required(str(encoded))
    accepts = required.get("accepts")
    if not isinstance(accepts, list) or len(accepts) != 1:
        raise StageAError("expected exactly one payment method")
    accepted = accepts[0]
    resource = required.get("resource") or {}
    observed = {
        "x402_version": required.get("x402Version"),
        "scheme": accepted.get("scheme"),
        "network": accepted.get("network"),
        "asset": accepted.get("asset"),
        "pay_to": accepted.get("payTo"),
        "quote_atomic_usdc": int(accepted.get("amount", -1)),
        "resource_url": resource.get("url"),
    }
    mismatches = {
        key: {"expected": value, "observed": observed.get(key)}
        for key, value in EXPECTED.items()
        if observed.get(key) != value
    }
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StageAError("HTTP 402 body is not valid JSON") from exc
    if body.get("error") != "PAYMENT-SIGNATURE required":
        mismatches["body_error"] = {
            "expected": "PAYMENT-SIGNATURE required",
            "observed": body.get("error"),
        }
    if mismatches:
        raise StageAError(
            "live Stage A contract drifted: "
            + json.dumps(mismatches, sort_keys=True))
    return {
        "status": "verified_unpaid",
        "tool": "regulatory-radar.scan_regulations",
        "request_sha256": REQUEST_SHA256,
        **observed,
        "payment_state": "required_unpaid",
        "mesh_peer_id": "must_be_filled_from_mesh_transport_proof",
        "payer_address": "omitted",
        "private_key": "never_present",
    }


def main() -> int:
    try:
        result = probe()
    except (StageAError, OSError, ValueError) as exc:
        print(json.dumps({
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
