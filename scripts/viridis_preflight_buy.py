#!/usr/bin/env python3
"""Preview one Security Preflight quote; purchase only with --pay and a cap.

Paid mode needs x402[requests,evm]==2.16.0 and X402_BUYER_PRIVATE_KEY in the
buyer's environment. No wallet is loaded in default quote mode. A paid call
is attempted once, never redirected or automatically retried. The complete
response stays in a private local file for inspection and future change checks.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

from viridis_preflight_watch import baseline_from_paid_result

BASE = "https://mcp.viridis-security.com"
URL = BASE + "/x402/security-preflight/security_preflight"
NETWORK = "eip155:8453"
ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
RECIPIENT = "0xfEf2e570b645EB720Ee6c589d27450810982f329"


class BuyerError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(payload_bytes, headers, timeout):
    request = urllib.request.Request(URL, data=payload_bytes, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "viridis-preflight-buyer/1.0", **headers,
    })
    try:
        response = urllib.request.build_opener(NoRedirect).open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = {"non_json_response": True}
        return response.code, dict(response.headers), body


def atomic(value):
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount <= 0:
            raise ValueError()
        scaled = amount * 1_000_000
        if scaled != scaled.to_integral_value():
            raise ValueError()
        return int(scaled)
    except (InvalidOperation, ValueError, OverflowError):
        raise argparse.ArgumentTypeError("use a positive USDC amount with at most six decimals")


def quote(response, cap=None):
    status, headers, _ = response
    if status != 402:
        raise BuyerError(f"Expected an unpaid HTTP 402 quote; received HTTP {status}.")
    try:
        encoded = next(v for k, v in headers.items() if k.lower() == "payment-required")
        required = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True))
        if (required["x402Version"] != 2 or required["resource"]["url"] != URL
                or len(required["accepts"]) != 1):
            raise ValueError()
        terms = required["accepts"][0]
        if (terms["scheme"] != "exact" or terms["network"] != NETWORK
                or terms["asset"].lower() != ASSET.lower()
                or terms["payTo"].lower() != RECIPIENT.lower()):
            raise ValueError()
        amount = int(terms["amount"])
        if (str(amount) != terms["amount"] or amount <= 0
                or not 0 < terms["maxTimeoutSeconds"] <= 300):
            raise ValueError()
    except (AssertionError, KeyError, ValueError, TypeError, AttributeError, StopIteration):
        raise BuyerError("Quote does not match the supported Security URL, Base USDC, recipient and terms.") from None
    if cap is not None and amount > cap:
        raise BuyerError("Quote exceeds --max-payment-usdc; no payment was attempted.")
    return required


class Signer:
    def __init__(self):
        try:
            from eth_account import Account
            from x402 import x402ClientSync
            from x402.mechanisms.evm.exact import ExactEvmScheme
        except ImportError:
            raise BuyerError('Install paid-mode dependencies: python -m pip install "x402[requests,evm]==2.16.0"') from None
        key = os.environ.get("X402_BUYER_PRIVATE_KEY", "").strip()
        if not key:
            raise BuyerError("Paid mode requires X402_BUYER_PRIVATE_KEY in your local environment.")
        try:
            self.account = Account.from_key(key)
        except Exception:
            raise BuyerError("The local buyer key is invalid.") from None
        self.address = self.account.address
        self.client = x402ClientSync().register(NETWORK, ExactEvmScheme(self.account))

    def sign(self, required):
        from x402.http import encode_payment_signature_header
        from x402.schemas import PaymentRequired
        # Sign only the exact, validated quote. The HTTP layer has no retry or
        # alternative-payment selector that could replace these checked terms.
        value = PaymentRequired.model_validate(required)
        return encode_payment_signature_header(self.client.create_payment_payload(value))


def save(handle, value):
    handle.seek(0)
    json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
    handle.write("\n")
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def run(inputs, *, pay=False, cap=None, output=None, timeout=30, source=None,
        transport=post, signer_factory=Signer):
    if not isinstance(inputs, dict) or not inputs.get("agent_id") or not isinstance(inputs.get("manifest"), dict):
        raise BuyerError("Inputs must contain agent_id and a manifest object.")
    if pay and (cap is None or output is None):
        raise BuyerError("Paid mode requires --max-payment-usdc and a new --output file.")
    payload = json.dumps(inputs, allow_nan=False, separators=(",", ":")).encode()
    headers = {"X-Viridis-Acquisition-Source": source} if source else {}
    signer = signer_factory() if pay else None
    if signer:
        headers["X402-Payer-Address"] = signer.address
    required = quote(transport(payload, headers, timeout), cap)
    terms = required["accepts"][0]
    summary = {"status": "QUOTE_READY", "resource": URL, "payment_attempted": False,
               "amount_usdc": format(Decimal(terms["amount"]) / 1_000_000, "f"),
               "network": NETWORK, "asset": ASSET, "recipient": RECIPIENT}
    if not pay:
        return summary
    # Reserve writable storage before signing. Never overwrite a prior result,
    # and retain an uncertainty marker if an interrupted payment may settle.
    try:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        raise BuyerError("Cannot reserve --output; use a new file in an existing writable directory.") from None
    with os.fdopen(fd, "w") as handle:
        save(handle, {"status": "PAYMENT_NOT_ATTEMPTED", "quote": summary})
        try:
            signature = signer.sign(required)
        except Exception:
            raise BuyerError("Signing failed before a paid HTTP request. No automatic retry was made.") from None
        save(handle, {"status": "PAYMENT_OUTCOME_UNKNOWN", "quote": summary,
                      "note": "If interrupted, reconcile with the seller and wallet before another purchase."})
        try:
            status, _, body = transport(payload, {**headers, "PAYMENT-SIGNATURE": signature}, timeout)
        except Exception:
            raise BuyerError("Payment outcome unknown. Inspect the reserved output and reconcile before retrying.") from None
        # Save the whole response, including any buyer-only feedback token,
        # privately before interpreting it. Never print that response or token.
        save(handle, body)
        if status != 200:
            raise BuyerError(f"Paid request returned HTTP {status}. Response saved; reconcile before retrying.")
        try:
            receipt = baseline_from_paid_result(body)
        except (ValueError, TypeError, AttributeError):
            raise BuyerError("Response saved but its delivery evidence did not validate. Reconcile before retrying.") from None
    return {**summary, "status": "PAID_RESULT_SAVED", "payment_attempted": True,
            "receipt_id": receipt, "output": str(output),
            "next": "Inspect findings, then pass this file to viridis_preflight_watch.py --paid-result.",
            "verification": "Local delivery hashes checked; buyer acceptance and server signature verification are separate."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--pay", action="store_true", help="Authorize exactly one purchase attempt within the explicit cap")
    parser.add_argument("--max-payment-usdc", type=atomic)
    parser.add_argument("--output", type=Path, help="New private result file; existing files are never overwritten")
    parser.add_argument("--timeout", type=int, default=30, choices=range(1, 121), metavar="SECONDS")
    parser.add_argument("--source", choices=("github", "direct", "search", "internal", "other"), help="Actual acquisition source, if known; never invent one")
    args = parser.parse_args(argv)
    try:
        result = run(json.loads(args.inputs.read_text()), pay=args.pay,
                     cap=args.max_payment_usdc, output=args.output,
                     timeout=args.timeout, source=args.source)
        print(json.dumps(result, indent=2))
        return 0
    except BuyerError as exc:
        print(json.dumps({"status": "STOPPED", "message": str(exc)}), file=sys.stderr)
    except (ValueError, OSError):
        print(json.dumps({"status": "STOPPED", "message": "Input or network error; inspect any output file before retrying."}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
