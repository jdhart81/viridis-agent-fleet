"""
x402_rail.py — standards-compliant x402 autonomous payment for the gate.

The restoration of "no human per tool call": an agent that holds USDC pays
per request, no account, no card. This module is the SETTLEMENT ADAPTER
only — pure logic + a facilitator HTTP client. It never touches the gate's
credit ledger directly; payment_gate.py calls it and, on a settled
payment, grants credits through the SAME path a funded escrow uses
(PR4 — x402 is a funding source, not a parallel ledger).

Facilitator-agnostic by design (PR): the same interface serves the
Coinbase CDP non-custodial facilitator (Phase 1, Base USDC) and, later,
Stripe's x402/PaymentIntents path — only the base URL + auth differ.

--- INVARIANTS (spec-invariance contract, PR-series) ---
PRX1 ADVERTISE: build_accepts() emits a standards-compliant x402
     PaymentRequirements object (scheme=exact, network, maxAmountRequired
     in atomic USDC, payTo=the Viridis address, asset=USDC contract).
     Additive to the existing envelope; absent when X402 is disabled.
PRX2 EXACT MATCH: a payment is acceptable only if scheme/network/asset/
     payTo match what we advertised AND the paid amount >= required.
     Any mismatch is a fail-closed refusal (PRX5), never a partial credit.
PRX3 VERIFY-THEN-SETTLE: the facilitator /verify must pass BEFORE the
     paid tool runs; /settle (which moves the money) is called only after
     a successful verify. On the gate side, settle precedes serving.
PRX4 EXACTLY-ONCE: settlement returns an on-chain tx hash; the caller
     (payment_gate) uses it as the idempotency key. This module is
     stateless — it never double-settles because it only settles when
     asked, and the gate guards replays by hash.
PRX5 FAIL-CLOSED: any error — network, facilitator, malformed header,
     amount/asset/address mismatch, disabled config — returns a
     structured refusal, never raises into the tool call, never grants.
PRX6 NO CUSTODY, NO KEYS: this module never holds funds or private keys;
     the CDP facilitator is non-custodial and settles directly to the
     Viridis address from env. It reads config from env only.
PRX7 KILL SWITCH: is_enabled() is false unless X402_ENABLED=1 AND an
     address AND a facilitator URL are configured. Disabled => the gate
     behaves exactly as it does today (Stripe checkout + internal ledger).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets as _secrets
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("viridis.x402")

X402_VERSION = 1
# USDC has 6 decimals. price_minor is USD cents. cents -> atomic USDC:
#   dollars = cents/100 ; atomic = dollars * 10^6 = cents * 10^4
USDC_ATOMIC_PER_CENT = 10_000
BASE_MAINNET_NETWORKS = frozenset({"base", "eip155:8453"})
BASE_MAINNET_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def is_enabled() -> bool:
    """PRX7: the rail is live only when explicitly armed AND configured."""
    return (os.environ.get("X402_ENABLED", "0") == "1"
            and bool(os.environ.get("VIRIDIS_X402_ADDRESS"))
            and bool(os.environ.get("X402_FACILITATOR_URL")))


def _cfg() -> dict:
    network = os.environ.get("X402_NETWORK", "base")
    asset = os.environ.get("X402_ASSET", BASE_MAINNET_USDC)
    return {
        "pay_to": os.environ.get("VIRIDIS_X402_ADDRESS", ""),
        "facilitator": os.environ.get("X402_FACILITATOR_URL", "").rstrip("/"),
        "network": network,
        # USDC contract on Base mainnet (override per network/testnet via env).
        "asset": asset,
        # EIP-712 token-domain metadata is chain-specific. Native USDC on
        # Base mainnet signs as "USD Coin"; Base Sepolia signs as "USDC".
        # Keep both fields configurable for future assets/networks.
        "asset_name": os.environ.get("X402_ASSET_NAME", ""),
        "asset_version": os.environ.get("X402_ASSET_VERSION", "2"),
        # CDP auth: per-request Ed25519 JWT (NOT a static bearer). The key
        # material is the pair {id (UUID), secret (base64 Ed25519)}.
        "cdp_key_id": os.environ.get("CDP_API_KEY_ID", ""),
        "cdp_key_secret": os.environ.get("CDP_API_KEY_SECRET", ""),
        "timeout_s": int(os.environ.get("X402_TIMEOUT_S", "20")),
    }


def _asset_eip712_name(c: dict) -> str:
    """Return the exact token-domain name used for EIP-712 signing.

    A wrong name still produces a syntactically valid payment payload, but the
    CDP facilitator rejects it as ``invalid_payload``. Only apply the mainnet
    default when both the network and official USDC contract match; otherwise
    preserve the existing testnet/default name.
    """
    configured = str(c.get("asset_name", "")).strip()
    if configured:
        return configured
    network = str(c.get("network", ""))
    asset = str(c.get("asset", ""))
    if (network in BASE_MAINNET_NETWORKS
            and asset.lower() == BASE_MAINNET_USDC.lower()):
        return "USD Coin"
    return "USDC"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def cdp_jwt(key_id: str, key_secret_b64: str, method: str,
            host: str, path: str) -> str:
    """CDP request-bound Ed25519 JWT (fixed 2026-07-18 per Sol's finding:
    CDP requires a fresh JWT signed with the API key's Ed25519 secret,
    bound to METHOD host+path, ~2 min expiry — NOT a static bearer).
    docs.cdp.coinbase.com/api-reference/v2/authentication."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey)
    raw = base64.b64decode(key_secret_b64)
    # CDP Ed25519 secret is base64 of the 64-byte libsodium secret key
    # (32-byte seed || 32-byte public); the signing seed is the first 32.
    seed = raw[:32]
    signer = Ed25519PrivateKey.from_private_bytes(seed)
    now = int(time.time())
    header = {"typ": "JWT", "alg": "EdDSA", "kid": key_id,
              "nonce": _secrets.token_hex(16)}
    claims = {"sub": key_id, "iss": "cdp", "aud": ["cdp_service"],
              "nbf": now, "exp": now + 120,
              "uris": [f"{method.upper()} {host}{path}"]}
    signing_input = (_b64url(json.dumps(header, separators=(",", ":")).encode())
                     + "." +
                     _b64url(json.dumps(claims, separators=(",", ":")).encode()))
    sig = signer.sign(signing_input.encode("ascii"))
    return signing_input + "." + _b64url(sig)


def price_atomic(price_minor: int) -> str:
    """USD cents -> atomic USDC string (PRX1)."""
    return str(int(price_minor) * USDC_ATOMIC_PER_CENT)


def build_accepts(name: str, price_minor: int, resource_url: str,
                  cfg: Optional[dict] = None) -> Optional[dict]:
    """PRX1: the x402 PaymentRequirements the 402 envelope advertises.
    Returns None when the rail is disabled (envelope stays pre-x402)."""
    if not is_enabled():
        return None
    c = cfg or _cfg()
    return {
        "scheme": "exact",
        "network": c["network"],
        "maxAmountRequired": price_atomic(price_minor),
        "resource": resource_url,
        "description": f"Viridis {name} tool call",
        "mimeType": "application/json",
        "payTo": c["pay_to"],
        "maxTimeoutSeconds": 120,
        "asset": c["asset"],
        "extra": {
            "name": _asset_eip712_name(c),
            "version": str(c.get("asset_version", "2")),
        },
    }


def parse_payment_header(header_value: Any) -> Optional[dict]:
    """Decode the client's X-PAYMENT header (base64 JSON). PRX5: any
    malformed input returns None, never raises."""
    if not isinstance(header_value, str) or not header_value.strip():
        return None
    try:
        raw = base64.b64decode(header_value.strip(), validate=True)
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:                                          # PRX5
        return None


def _post(url: str, body: dict, c: dict, timeout_s: int) -> dict:
    """POST to the CDP facilitator with a fresh request-bound Ed25519 JWT
    (PRX/CDP auth). `c` carries the key pair + config."""
    parts = urllib.parse.urlsplit(url)
    host, path = parts.netloc, parts.path
    data = json.dumps(body).encode("utf-8")
    headers = {"content-type": "application/json"}
    if c.get("cdp_key_id") and c.get("cdp_key_secret"):
        token = cdp_jwt(c["cdp_key_id"], c["cdp_key_secret"],
                        "POST", host, path)
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verify_and_settle(
        payment_payload: dict, requirements: dict,
        cfg: Optional[dict] = None,
        _transport: Optional[Callable[[str, dict, str, int], dict]] = None,
) -> dict:
    """PRX2/PRX3/PRX4/PRX5: verify the payment against what we advertised,
    then settle it on-chain via the facilitator. Returns:
        {"settled": True,  "tx_hash": "0x…", "network": "base",
         "amount_atomic": "250000"}
      | {"settled": False, "reason": "<why>"}
    Never raises. `_transport` is injectable for tests (mock facilitator)."""
    c = cfg or _cfg()
    post = _transport or (lambda u, b: _post(u, b, c, c["timeout_s"]))
    try:
        if not is_enabled():
            return {"settled": False, "reason": "x402_disabled"}
        if not isinstance(payment_payload, dict) or not payment_payload:
            return {"settled": False, "reason": "missing_or_malformed_payment"}
        # PRX2: the client must be paying for exactly what we advertised.
        if payment_payload.get("network") != requirements["network"]:
            return {"settled": False, "reason": "network_mismatch"}
        if str(payment_payload.get("scheme", "exact")) != requirements["scheme"]:
            return {"settled": False, "reason": "scheme_mismatch"}
        base = c["facilitator"]
        verify = post(f"{base}/verify",
                      {"x402Version": X402_VERSION,
                       "paymentPayload": payment_payload,
                       "paymentRequirements": requirements})
        if not (isinstance(verify, dict) and verify.get("isValid") is True):
            reason = (verify.get("invalidReason")
                      if isinstance(verify, dict) else "verify_failed")
            return {"settled": False, "reason": f"verify:{reason}"}
        # PRX3: only settle after a passing verify.
        settle = post(f"{base}/settle",
                      {"x402Version": X402_VERSION,
                       "paymentPayload": payment_payload,
                       "paymentRequirements": requirements})
        if not (isinstance(settle, dict) and settle.get("success") is True):
            reason = (settle.get("errorReason")
                      if isinstance(settle, dict) else "settle_failed")
            return {"settled": False, "reason": f"settle:{reason}"}
        tx = settle.get("transaction") or settle.get("txHash")
        if not tx:
            return {"settled": False, "reason": "settle:no_tx_hash"}
        return {"settled": True, "tx_hash": str(tx),
                "network": requirements["network"],
                "amount_atomic": requirements["maxAmountRequired"],
                "settlement_receipt": settle}
    except Exception as exc:                                   # PRX5 fail-closed
        logger.warning("x402 verify/settle failed (%s) — refusing, no grant",
                       type(exc).__name__)
        return {"settled": False, "reason": f"exception:{type(exc).__name__}"}
