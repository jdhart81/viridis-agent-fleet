#!/usr/bin/env python3
"""Inspect one Viridis Regulatory Radar x402 v2 quote without paying."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any, Callable


DEFAULT_BASE_URL = "https://mcp.viridisconservation.com"
ROUTE = "/x402/regulatory-radar/scan_regulations"
BASE_NETWORK = "eip155:8453"
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
MAX_BODY_BYTES = 1_000_000


class PreflightError(RuntimeError):
    """Raise when the unpaid contract is missing or differs from the mandate."""


def _usdc_to_atomic(value: str) -> int:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "must be positive USDC with at most 6 decimals"
        ) from exc
    atomic = amount * Decimal(1_000_000)
    if amount <= 0 or atomic != atomic.to_integral_value():
        raise argparse.ArgumentTypeError(
            "must be positive USDC with at most 6 decimals"
        )
    return int(atomic)


def _decode_payment_required(value: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        decoded = json.loads(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightError(
            "PAYMENT-REQUIRED is not valid base64url JSON"
        ) from exc
    if not isinstance(decoded, dict):
        raise PreflightError("PAYMENT-REQUIRED must decode to an object")
    return decoded


def _build_request(
    endpoint: str,
    jurisdiction: str,
    sector: str,
    query: str = "",
    payer: str = "",
) -> tuple[urllib.request.Request, bytes]:
    payload = {"jurisdiction": jurisdiction, "sector": sector}
    if query:
        payload["query"] = query
    request_bytes = json.dumps(
        payload, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "openclaw-viridis-radar-preflight/1.0",
    }
    if payer:
        headers["X402-Payer-Address"] = payer
    return (
        urllib.request.Request(
            endpoint,
            data=request_bytes,
            headers=headers,
            method="POST",
        ),
        request_bytes,
    )


def _fetch(
    request: urllib.request.Request, timeout: float
) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
            return response.status, dict(response.headers), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read(MAX_BODY_BYTES + 1)
        return exc.code, dict(exc.headers), raw


def _inspect(
    status: int,
    headers: dict[str, str],
    raw: bytes,
    expected_resource: str,
    max_atomic: int,
    request_sha256: str,
) -> dict[str, Any]:
    if len(raw) > MAX_BODY_BYTES:
        raise PreflightError("response body exceeds size cap")
    if status != 402:
        raise PreflightError(f"expected HTTP 402, received {status}")
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    encoded = normalized.get("payment-required")
    if not encoded:
        raise PreflightError("HTTP 402 omitted PAYMENT-REQUIRED")
    required = _decode_payment_required(encoded)
    if required.get("x402Version") != 2:
        raise PreflightError("expected x402Version 2")
    resource = required.get("resource")
    if not isinstance(resource, dict) or resource.get("url") != expected_resource:
        raise PreflightError("payment resource does not match the requested route")
    accepts = required.get("accepts")
    if not isinstance(accepts, list) or not accepts:
        raise PreflightError("PAYMENT-REQUIRED has no accepted payment method")
    accepted = next(
        (
            item
            for item in accepts
            if isinstance(item, dict)
            and item.get("scheme") == "exact"
            and item.get("network") == BASE_NETWORK
            and item.get("asset") == BASE_USDC
        ),
        None,
    )
    if accepted is None:
        raise PreflightError(
            "no exact Base-mainnet official-USDC payment method"
        )
    try:
        amount = int(accepted.get("amount"))
    except (TypeError, ValueError) as exc:
        raise PreflightError("payment amount is not an integer") from exc
    if amount <= 0:
        raise PreflightError("payment amount must be positive")
    if amount > max_atomic:
        raise PreflightError(
            f"quote {amount} atomic USDC exceeds ceiling {max_atomic}"
        )
    pay_to = accepted.get("payTo")
    if not isinstance(pay_to, str) or not pay_to:
        raise PreflightError("payment receiver is missing")
    return {
        "status": "verified_unpaid",
        "payment_state": "required_unpaid",
        "resource": expected_resource,
        "x402_version": 2,
        "scheme": "exact",
        "network": BASE_NETWORK,
        "asset": BASE_USDC,
        "pay_to": pay_to,
        "amount_atomic_usdc": amount,
        "amount_usdc": f"{Decimal(amount) / Decimal(1_000_000):.6f}",
        "ceiling_atomic_usdc": max_atomic,
        "request_sha256": request_sha256,
        "payment_attempted": False,
    }


def preflight(
    jurisdiction: str,
    sector: str,
    query: str = "",
    payer: str = "",
    max_atomic: int = 250_000,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 20.0,
    fetch: Callable[
        [urllib.request.Request, float],
        tuple[int, dict[str, str], bytes],
    ] = _fetch,
) -> dict[str, Any]:
    if not jurisdiction.strip() or not sector.strip():
        raise PreflightError("jurisdiction and sector are required")
    endpoint = base_url.rstrip("/") + ROUTE
    request, request_bytes = _build_request(
        endpoint,
        jurisdiction.strip(),
        sector.strip(),
        query.strip(),
        payer.strip(),
    )
    status, headers, raw = fetch(request, timeout)
    return _inspect(
        status,
        headers,
        raw,
        endpoint,
        max_atomic,
        hashlib.sha256(request_bytes).hexdigest(),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect one live Regulatory Radar x402 quote without paying"
    )
    parser.add_argument("--jurisdiction", required=True)
    parser.add_argument("--sector", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument(
        "--payer",
        default="",
        help="optional public payer address used only as a pricing hint",
    )
    parser.add_argument(
        "--max-usdc",
        type=_usdc_to_atomic,
        default=_usdc_to_atomic("0.25"),
        metavar="USDC",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = preflight(
            jurisdiction=args.jurisdiction,
            sector=args.sector,
            query=args.query,
            payer=args.payer,
            max_atomic=args.max_usdc,
            base_url=args.base_url,
            timeout=args.timeout,
        )
    except (OSError, PreflightError) as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "payment_attempted": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
