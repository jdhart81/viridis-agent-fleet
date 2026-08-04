#!/usr/bin/env python3
"""Buy one PayanAgent offer with x402 Exact / ERC-3009 Base USDC.

Dependencies (Python 3.10+):
    python -m pip install 'x402[requests,evm]==2.18.0'

The private key is read only from PAYANAGENT_WALLET_PRIVATE_KEY. The script
preflights the unpaid 402 challenge and refuses non-Base, non-USDC, malformed,
or over-cap terms before the x402 SDK is allowed to sign anything.
"""

from __future__ import annotations

import argparse
import base64
from decimal import Decimal, InvalidOperation
import json
import os
import re
import sys
from typing import Any


BASE_URL = "https://payanagent.com"
BASE_NETWORK = "eip155:8453"
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
KEY_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
RECEIPT_RE = re.compile(r"^kn[0-9a-z]+$")
TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def decode_payment_required(raw_header: str) -> dict[str, Any]:
    """Decode one x402 v2 PAYMENT-REQUIRED base64 JSON header."""
    if not raw_header:
        raise ValueError("missing PAYMENT-REQUIRED header")
    try:
        padded = raw_header + "=" * (-len(raw_header) % 4)
        decoded = base64.b64decode(padded, validate=True).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as exc:
        raise ValueError("invalid PAYMENT-REQUIRED header") from exc
    if not isinstance(payload, dict):
        raise ValueError("PAYMENT-REQUIRED must decode to an object")
    return payload


def validate_terms(payment_required: dict[str, Any], max_usd: Decimal) -> dict[str, Any]:
    """Return the one accepted Base-USDC exact requirement or fail closed."""
    if payment_required.get("x402Version") != 2:
        raise ValueError("only x402 version 2 is accepted")
    accepts = payment_required.get("accepts")
    if not isinstance(accepts, list):
        raise ValueError("payment challenge has no accepts list")
    matches = [
        row
        for row in accepts
        if isinstance(row, dict)
        and row.get("scheme") == "exact"
        and row.get("network") == BASE_NETWORK
        and str(row.get("asset", "")).lower() == BASE_USDC.lower()
    ]
    if len(matches) != 1:
        raise ValueError("challenge must contain exactly one Base-USDC exact requirement")
    requirement = matches[0]
    if not ADDRESS_RE.fullmatch(str(requirement.get("payTo", ""))):
        raise ValueError("payment recipient is not a valid EVM address")
    try:
        amount_atomic = int(str(requirement.get("amount", "")))
    except ValueError as exc:
        raise ValueError("payment amount is not an integer") from exc
    if amount_atomic <= 0:
        raise ValueError("payment amount must be positive")
    amount_usd = Decimal(amount_atomic) / Decimal(1_000_000)
    if amount_usd > max_usd:
        raise ValueError(f"payment ${amount_usd} exceeds cap ${max_usd}")
    return requirement


def parse_input(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("--input-json must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("--input-json must be a JSON object")
    return value


def execute_purchase(offer_id: str, input_payload: dict[str, Any], max_usd: Decimal) -> dict[str, Any]:
    """Preflight, sign, settle, and verify one PayanAgent purchase."""
    try:
        import requests
        from eth_account import Account
        from x402 import x402ClientSync
        from x402.http.clients import x402_requests
        from x402.mechanisms.evm import EthAccountSigner
        from x402.mechanisms.evm.exact.register import register_exact_evm_client
    except ImportError as exc:
        raise RuntimeError("install dependencies with: pip install 'x402[requests,evm]==2.18.0'") from exc

    private_key = os.environ.get("PAYANAGENT_WALLET_PRIVATE_KEY", "")
    if not KEY_RE.fullmatch(private_key):
        raise RuntimeError("PAYANAGENT_WALLET_PRIVATE_KEY must be one 0x-prefixed EVM key")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", offer_id):
        raise RuntimeError("offer id contains invalid characters")

    url = f"{BASE_URL}/x402/{offer_id}"
    unpaid = requests.post(url, json=input_payload, timeout=30)
    if unpaid.status_code != 402:
        raise RuntimeError(f"unpaid preflight expected HTTP 402, got {unpaid.status_code}")
    raw_terms = unpaid.headers.get("PAYMENT-REQUIRED") or unpaid.headers.get("X-PAYMENT-REQUIRED")
    terms = decode_payment_required(raw_terms or "")
    accepted = validate_terms(terms, max_usd)

    account = Account.from_key(private_key)
    client = x402ClientSync()
    register_exact_evm_client(client, EthAccountSigner(account))
    with x402_requests(client) as session:
        response = session.post(url, json=input_payload, timeout=60)

    response_body = response.text
    if not response.ok:
        raise RuntimeError(f"paid request failed with HTTP {response.status_code}: {response_body[:500]}")
    receipt_id = response.headers.get("X-Receipt-Id", "")
    tx_hash = response.headers.get("X-Tx-Hash", "")
    if not RECEIPT_RE.fullmatch(receipt_id):
        raise RuntimeError("paid response returned no valid X-Receipt-Id")
    if not TX_RE.fullmatch(tx_hash):
        raise RuntimeError("paid response returned no valid X-Tx-Hash")

    receipt_response = requests.get(f"{BASE_URL}/api/v1/receipts/{receipt_id}", timeout=30)
    if not receipt_response.ok:
        raise RuntimeError(f"public receipt lookup failed with HTTP {receipt_response.status_code}")
    receipt_text = receipt_response.text.lower()
    if receipt_id.lower() not in receipt_text or tx_hash.lower() not in receipt_text:
        raise RuntimeError("public receipt does not bind the returned receipt id and tx hash")

    try:
        output: Any = response.json()
    except ValueError:
        output = response_body
    return {
        "offerId": offer_id,
        "payer": account.address,
        "payTo": accepted["payTo"],
        "amountAtomicUsdc": str(accepted["amount"]),
        "response": output,
        "receiptId": receipt_id,
        "txHash": tx_hash,
        "receiptVerified": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("offer_id")
    parser.add_argument("--input-json", required=True, help="JSON object matching the offer input schema")
    parser.add_argument("--max-usd", default="0.01", help="hard maximum paid amount, default 0.01")
    parser.add_argument("--execute", action="store_true", help="authorize one capped x402 signature and POST")
    args = parser.parse_args(argv)

    if not args.execute:
        parser.error("refusing to pay without --execute")
    try:
        max_usd = Decimal(args.max_usd)
    except InvalidOperation as exc:
        raise SystemExit("--max-usd must be a decimal number") from exc
    if max_usd <= 0 or max_usd > Decimal("0.01"):
        raise SystemExit("--max-usd must be greater than 0 and at most 0.01")
    try:
        payload = parse_input(args.input_json)
        result = execute_purchase(args.offer_id, payload, max_usd)
    except (RuntimeError, ValueError) as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
