#!/usr/bin/env python3
"""Buyer-owned change check suitable for a release pipeline or scheduler.

Reads the buyer's current JSON and optional saved paid result, checks its
delivery digest locally, then asks the free watch endpoint whether another
assessment is needed. Never signs, pays, records feedback, or scans a runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from viridis_adoption_client import _post, DEFAULT_BASE_URL


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def baseline_from_paid_result(result):
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise ValueError("expected a successful saved paid result")
    delivery = result.get("viridis_delivery", {})
    if delivery.get("version") != "viridis-paid-delivery-v1":
        raise ValueError("missing supported delivery receipt")
    if delivery.get("route") != "security-preflight/security_preflight":
        raise ValueError("saved result belongs to another route")
    content = {k: v for k, v in result.items() if k != "viridis_delivery"}
    if _digest(content) != delivery.get("result_sha256"):
        raise ValueError("saved result digest mismatch")
    receipt = {k: v for k, v in delivery.items() if k != "receipt_sha256"}
    if _digest(receipt) != delivery.get("receipt_sha256"):
        raise ValueError("delivery receipt digest mismatch")
    if not delivery.get("settlement", {}).get("transaction"):
        raise ValueError("missing settlement reference")
    baseline = result.get("receipt", {}).get("receipt_id")
    if not isinstance(baseline, str):
        raise ValueError("missing security baseline receipt")
    # Hashes establish file consistency only; the server independently checks
    # its authentic stored assessment. Payment verification remains separate.
    return baseline


def check(base_url, inputs, baseline_receipt_id=None, timeout=20):
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base URL must be HTTPS without credentials, query, or fragment")
    response = _post(base_url.rstrip("/") + "/security-preflight/watch", {
        "inputs": inputs, "baseline_receipt_id": baseline_receipt_id,
    }, timeout)
    if response["status_code"] != 200:
        raise ValueError(f"watch returned HTTP {response['status_code']}")
    result = response["body"]
    if result.get("version") != "viridis-preflight-watch-v1" or result.get("decision") not in {
            "BASELINE_REQUIRED", "UNCHANGED", "RECHECK_REQUIRED"}:
        raise ValueError("unsupported watch response")
    if result.get("payment_authorized") is not False or result.get("tool_executed") is not False:
        raise ValueError("watch violated read-only contract")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True,
                        help="Current caller-owned assessment JSON")
    baseline = parser.add_mutually_exclusive_group()
    baseline.add_argument("--paid-result", type=Path, help="Saved complete paid response JSON")
    baseline.add_argument("--baseline-receipt-id")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    try:
        baseline_id = (baseline_from_paid_result(json.loads(args.paid_result.read_text()))
                       if args.paid_result else args.baseline_receipt_id)
        result = check(args.base_url, json.loads(args.inputs.read_text()), baseline_id, args.timeout)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc), "payment_attempted": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
