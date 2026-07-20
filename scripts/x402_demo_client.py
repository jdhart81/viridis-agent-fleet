#!/usr/bin/env python3
"""Viridis x402 buyer demo: measure -> account -> disclose -> claim -> scan.

Install (demo machine only; this SDK is NOT in the gateway image):
  python3 -m pip install "x402[requests,evm]==2.16.0"

Free discovery run (prints every live 402 challenge; moves no money):
  python3 scripts/x402_demo_client.py --dry-run

Paid Base-mainnet run (wallet needs Base USDC; never paste the key in code):
  export X402_BUYER_PRIVATE_KEY='0x...'
  python3 scripts/x402_demo_client.py

The five list prices total $5.75 USDC ($0.50 + $1 + $2 + $2 + $0.25).
If x402-intro-v1 is later enabled, a wallet's first route is $0.01 and the
same chain totals $5.26. The deployment keeps that switch OFF until Justin
explicitly approves activation.

CDP Bazaar merchant inventory:
https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0xfEf2e570b645EB720Ee6c589d27450810982f329
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional


DEFAULT_BASE_URL = "https://mcp.viridisconservation.com"
BAZAAR_MERCHANT_URL = (
    "https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant"
    "?payTo=0xfEf2e570b645EB720Ee6c589d27450810982f329")


@dataclass(frozen=True)
class Step:
    name: str
    agent: str
    tool: str
    value: str
    build_input: Callable[[dict], dict]

    def url(self, base_url: str) -> str:
        return f"{base_url.rstrip('/')}/x402/{self.agent}/{self.tool}"


def _takeoff_input(_: dict) -> dict:
    return {"items": [{
        "id": "demo-slab", "assembly": "concrete_slab",
        "unit_system": "imperial",
        "dimensions": {
            "length": {"value": "20", "unit": "ft"},
            "width": {"value": "30", "unit": "ft"},
            "thickness": {"value": "4", "unit": "in"},
        },
    }], "options": {"project_id": "x402-demo"}}


def _ghg_input(outputs: dict) -> dict:
    takeoff = outputs.get("measure", {})
    takeoff_data = takeoff.get("data", takeoff) if isinstance(takeoff, dict) else {}
    return {
        "activities": [{
            "id": "demo-grid-electricity",
            "activity_type": "purchased_electricity",
            "quantity": "1000", "unit": "kwh", "region": "US",
            "year": 2023,
        }],
        "options": {
            "project_id": "x402-demo",
            "source_takeoff_audit_sha256": takeoff_data.get("audit_sha256"),
        },
    }


def _disclosure_input(outputs: dict) -> dict:
    account = outputs.get("account")
    ghg_result = (account.get("data", account)
                  if isinstance(account, dict) else account)
    return {
        "framework": "esrs-e1",
        "company_facts": {
            "company_name": "Example Climate Works",
            "reporting_period": "2026",
            "transition_plan": {"status": "board-approved",
                                "target_year": 2035},
            "climate_targets": {"scope": "Scopes 1-3",
                                "target": "50% by 2035"},
        },
        "ghg_result": ghg_result,
        "options": {"applicability": {
            "framework": "esrs-e1", "applies": True,
            "reason": "demo company is preparing an ESRS E1 disclosure",
            "source": "buyer",
        }},
    }


def _tax_input(outputs: dict) -> dict:
    disclosure = outputs.get("disclose", {})
    data = disclosure.get("data", disclosure) if isinstance(disclosure, dict) else {}
    return {
        "credit": "45V",
        "facts": {
            "tax_year": 2026,
            "source_disclosure_audit_sha256": data.get("audit_sha256"),
        },
    }


def _radar_input(outputs: dict) -> dict:
    tax = outputs.get("claim", {})
    data = tax.get("data", tax) if isinstance(tax, dict) else {}
    credit = data.get("credit", "45V")
    return {"jurisdiction": "US", "sector": "energy",
            "query": f"{credit} clean energy tax credit emissions disclosure"}


STEPS = (
    Step("measure", "quantity-takeoff", "calculate_takeoff", "$0.50",
         _takeoff_input),
    Step("account", "ghg-ledger", "calculate_inventory", "$1.00",
         _ghg_input),
    Step("disclose", "disclosure-compiler", "compile_disclosure", "$2.00",
         _disclosure_input),
    Step("claim", "taxcredit-engine", "calculate_tax_credit", "$2.00",
         _tax_input),
    Step("scan", "regulatory-radar", "scan_regulations", "$0.25",
         _radar_input),
)


def _json_response(status: int, headers: Any, raw: bytes) -> dict:
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {"raw": raw.decode("utf-8", errors="replace")}
    return {"status": status, "headers": dict(headers), "body": body}


def _raw_post(url: str, payload: dict, timeout: int,
              payer_address: str = "") -> dict:
    headers = {"Content-Type": "application/json",
               "Accept": "application/json"}
    if payer_address:
        headers["X402-Payer-Address"] = payer_address
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers,
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _json_response(response.status, response.headers,
                                  response.read())
    except urllib.error.HTTPError as exc:
        return _json_response(exc.code, exc.headers, exc.read())


def _payment_required(response: dict) -> dict:
    headers = {str(k).lower(): v for k, v in response["headers"].items()}
    encoded = headers.get("payment-required")
    if encoded:
        padding = "=" * (-len(encoded) % 4)
        return json.loads(base64.b64decode(encoded + padding).decode("utf-8"))
    body = response.get("body") or {}
    if body.get("accepts"):
        return body
    raise RuntimeError("402 response did not include PAYMENT-REQUIRED/accepts")


def _amount_atomic(required: dict) -> int:
    accepted = required["accepts"][0]
    return int(accepted.get("amount", accepted.get("maxAmountRequired")))


def _display_challenge(step: Step, required: dict) -> None:
    accepted = required["accepts"][0]
    amount = _amount_atomic(required)
    print(f"\n[{step.name}] HTTP 402 from {step.agent}/{step.tool}")
    print(json.dumps({
        "scheme": accepted.get("scheme"),
        "network": accepted.get("network"),
        "asset": accepted.get("asset"),
        "amount_atomic": str(amount),
        "amount_usdc": f"{amount / 1_000_000:.2f}",
        "payTo": accepted.get("payTo"),
    }, indent=2))


class LiveBuyer:
    """Raw 402 inspection plus the official x402 SDK's requests adapter."""

    def __init__(self, private_key: str, timeout: int):
        try:
            import requests
            from eth_account import Account
            from x402 import x402ClientSync
            from x402.http.clients import x402_requests
            from x402.mechanisms.evm.exact import ExactEvmScheme
        except ImportError as exc:
            raise RuntimeError(
                'Paid mode requires: pip install "x402[requests,evm]==2.16.0"'
            ) from exc
        self.timeout = timeout
        self.account = Account.from_key(private_key)
        client = x402ClientSync()
        client.register("eip155:*", ExactEvmScheme(self.account))
        self.session = x402_requests(client)
        self.session.headers.update({
            "Accept": "application/json",
            "X402-Payer-Address": self.account.address,
        })
        self._requests = requests

    def challenge(self, url: str, payload: dict) -> dict:
        return _raw_post(url, payload, self.timeout, self.account.address)

    def pay(self, url: str, payload: dict) -> dict:
        response = self.session.post(url, json=payload, timeout=self.timeout)
        return {"status": response.status_code,
                "headers": dict(response.headers),
                "body": response.json()}


class DryRunBuyer:
    def __init__(self, timeout: int):
        self.timeout = timeout

    def challenge(self, url: str, payload: dict) -> dict:
        return _raw_post(url, payload, self.timeout)

    def pay(self, url: str, payload: dict) -> dict:  # pragma: no cover
        raise AssertionError("dry-run never pays")


def run_workflow(base_url: str, buyer: Any, dry_run: bool = False) -> dict:
    outputs: dict = {}
    total_atomic = 0
    for step in STEPS:
        payload = step.build_input(outputs)
        challenge = buyer.challenge(step.url(base_url), payload)
        if challenge["status"] != 402:
            raise RuntimeError(
                f"{step.name}: expected HTTP 402, got {challenge['status']}")
        required = _payment_required(challenge)
        _display_challenge(step, required)
        total_atomic += _amount_atomic(required)
        if dry_run:
            outputs[step.name] = {"dry_run": True, "input": payload}
            continue
        paid = buyer.pay(step.url(base_url), payload)
        if paid["status"] != 200:
            raise RuntimeError(
                f"{step.name}: paid request returned {paid['status']}: "
                f"{json.dumps(paid['body'], sort_keys=True)}")
        outputs[step.name] = paid["body"]
        print(f"[{step.name}] settled and returned:")
        print(json.dumps(paid["body"], indent=2, sort_keys=True))
    summary = {
        "workflow": "measure -> account -> disclose -> claim -> scan",
        "dry_run": dry_run,
        "quoted_total_atomic_usdc": total_atomic,
        "quoted_total_usdc": f"{total_atomic / 1_000_000:.2f}",
        "outputs": outputs,
    }
    print("\nComposed workflow output:")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run or inspect the five-step Viridis x402 workflow")
    parser.add_argument("--dry-run", action="store_true",
                        help="print live 402 requirements without paying")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)
    if args.dry_run:
        buyer = DryRunBuyer(args.timeout)
    else:
        private_key = os.environ.get("X402_BUYER_PRIVATE_KEY", "").strip()
        if not private_key:
            parser.error("paid mode requires X402_BUYER_PRIVATE_KEY")
        buyer = LiveBuyer(private_key, args.timeout)
    print(f"Viridis x402 workflow at {args.base_url}")
    print(f"Bazaar: {BAZAAR_MERCHANT_URL}")
    run_workflow(args.base_url, buyer, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
