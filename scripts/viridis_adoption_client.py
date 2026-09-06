#!/usr/bin/env python3
"""Select one Viridis tool and optionally fetch its unpaid x402 quote.

This stdlib-only client is safe for evaluation and CI. It never loads a
wallet, creates a payment signature, retries a paid request, or executes a
paid tool. A calling agent can use the returned integration contract to hand
the exact fresh quote to its own operator-controlled payment policy.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "https://mcp.viridisconservation.com"


def _post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "viridis-adoption-client/1.0",
        },
        method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        body = json.loads(raw.decode("utf-8")) if raw else {}
        return {
            "status_code": exc.code,
            "headers": {str(k).lower(): str(v) for k, v in exc.headers.items()},
            "body": body,
        }
    with response:
        raw = response.read()
        return {
            "status_code": response.status,
            "headers": {
                str(k).lower(): str(v) for k, v in response.headers.items()
            },
            "body": json.loads(raw.decode("utf-8")) if raw else {},
        }


def build_plan(
    base_url: str,
    objective: str,
    inputs: dict[str, Any],
    max_price_minor: int | None,
    timeout: float,
) -> dict[str, Any]:
    response = _post(base_url.rstrip("/") + "/adopt", {
        "objective": objective,
        "inputs": inputs,
        "max_price_minor": max_price_minor,
    }, timeout)
    if response["status_code"] != 200:
        raise RuntimeError(
            f"adoption endpoint returned HTTP {response['status_code']}: "
            f"{response['body']}")
    return response["body"]


def fetch_unpaid_quote(plan: dict[str, Any], timeout: float) -> dict[str, Any]:
    if plan.get("decision") != "READY_FOR_QUOTE":
        raise ValueError("adoption plan is not READY_FOR_QUOTE")
    integration = plan.get("integration")
    request = integration.get("quote_request") if isinstance(integration, dict) else None
    if not isinstance(request, dict):
        raise ValueError("adoption plan has no quote_request")
    response = _post(str(request["url"]), dict(request["body"]), timeout)
    if response["status_code"] != 402:
        raise RuntimeError(
            "expected an unpaid HTTP 402 quote; received "
            f"HTTP {response['status_code']}")
    required = response["headers"].get("payment-required")
    if not required:
        raise RuntimeError("HTTP 402 response has no PAYMENT-REQUIRED header")
    return {
        "status": "UNPAID_QUOTE_READY",
        "route": integration["route"],
        "request_url": request["url"],
        "request_body": request["body"],
        "payment_required": required,
        "payment_attempted": False,
        "wallet_loaded": False,
        "signature_created": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Select one Viridis tool and optionally fetch its unpaid x402 quote."
        ))
    parser.add_argument("objective")
    parser.add_argument("--inputs-json", type=json.loads, default={})
    parser.add_argument("--max-price-minor", type=int)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--fetch-quote", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not isinstance(args.inputs_json, dict):
        print("--inputs-json must decode to an object", file=sys.stderr)
        return 2
    if args.max_price_minor is not None and args.max_price_minor < 0:
        print("--max-price-minor must be non-negative", file=sys.stderr)
        return 2
    try:
        plan = build_plan(
            args.base_url,
            args.objective,
            args.inputs_json,
            args.max_price_minor,
            args.timeout,
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        if args.fetch_quote:
            print(json.dumps(
                fetch_unpaid_quote(plan, args.timeout),
                indent=2,
                sort_keys=True,
            ))
        return 0
    except Exception as exc:
        print(f"adoption probe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
