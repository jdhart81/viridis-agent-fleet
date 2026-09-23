#!/usr/bin/env python3
"""
PRX1-PRX7 — x402 settlement adapter, tested entirely against a MOCK
facilitator (no key, no chain, no funds). One test per claim.

Run:  pytest deploy/gateway/test_x402_rail.py -q
"""
import base64
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import x402_rail as x  # noqa: E402

CFG = {"pay_to": "0xViridisAddr", "facilitator": "https://fac.test",
       "network": "base", "asset": "0xUSDC", "api_key": "k", "timeout_s": 5}


def enabled(monkeypatch):
    monkeypatch.setenv("X402_ENABLED", "1")
    monkeypatch.setenv("VIRIDIS_X402_ADDRESS", "0xViridisAddr")
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://fac.test")


def reqs(price_minor=25):
    return x.build_accepts("regulatory-radar", price_minor,
                           "https://mcp.viridisconservation.com/regulatory-radar/mcp",
                           cfg=CFG)


def mock_transport(verify_ok=True, settle_ok=True, tx="0xabc"):
    def t(url, body):
        if url.endswith("/verify"):
            return {"isValid": verify_ok} if verify_ok else {
                "isValid": False, "invalidReason": "insufficient_funds"}
        if url.endswith("/settle"):
            return {"success": settle_ok, "transaction": tx} if settle_ok else {
                "success": False, "errorReason": "reverted"}
        raise AssertionError("unexpected url " + url)
    return t


def good_payment():
    return {"x402Version": 1, "scheme": "exact", "network": "base",
            "payload": {"signature": "0xsig"}}


# --- PRX7 kill switch -------------------------------------------------------- #
def test_PRX7_disabled_by_default(monkeypatch):
    monkeypatch.delenv("X402_ENABLED", raising=False)
    assert x.is_enabled() is False
    assert x.build_accepts("a", 25, "u") is None


def test_PRX7_needs_flag_address_and_facilitator(monkeypatch):
    monkeypatch.setenv("X402_ENABLED", "1")
    monkeypatch.delenv("VIRIDIS_X402_ADDRESS", raising=False)
    monkeypatch.delenv("X402_FACILITATOR_URL", raising=False)
    assert x.is_enabled() is False
    enabled(monkeypatch)
    assert x.is_enabled() is True


# --- PRX1 advertise ---------------------------------------------------------- #
def test_PRX1_accepts_is_standards_shaped(monkeypatch):
    enabled(monkeypatch)
    r = reqs(25)
    assert r["scheme"] == "exact" and r["network"] == "base"
    assert r["maxAmountRequired"] == "250000"        # $0.25 -> atomic USDC
    assert r["payTo"] == "0xViridisAddr" and r["asset"] == "0xUSDC"
    assert r["extra"] == {"name": "USDC", "version": "2"}


def test_PRX1_base_mainnet_usdc_uses_usd_coin_eip712_domain(monkeypatch):
    enabled(monkeypatch)
    mainnet_cfg = {
        **CFG,
        "network": "base",
        "asset": x.BASE_MAINNET_USDC,
    }
    r = x.build_accepts("regulatory-radar", 25, "https://example.test/mcp",
                        cfg=mainnet_cfg)
    assert r["extra"] == {"name": "USD Coin", "version": "2"}


def test_PRX1_base_sepolia_usdc_keeps_usdc_eip712_domain(monkeypatch):
    enabled(monkeypatch)
    sepolia_cfg = {
        **CFG,
        "network": "base-sepolia",
        "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    }
    r = x.build_accepts("regulatory-radar", 25, "https://example.test/mcp",
                        cfg=sepolia_cfg)
    assert r["extra"] == {"name": "USDC", "version": "2"}


def test_PRX1_asset_name_can_be_configured(monkeypatch):
    enabled(monkeypatch)
    custom_cfg = {**CFG, "asset_name": "Custom Stablecoin",
                  "asset_version": "7"}
    r = x.build_accepts("custom", 25, "https://example.test/mcp",
                        cfg=custom_cfg)
    assert r["extra"] == {"name": "Custom Stablecoin", "version": "7"}


def test_PRX1_price_atomic_math():
    assert x.price_atomic(25) == "250000"            # $0.25
    assert x.price_atomic(200) == "2000000"          # $2.00


# --- PRX2 exact match -------------------------------------------------------- #
def test_PRX2_network_mismatch_refused(monkeypatch):
    enabled(monkeypatch)
    p = {**good_payment(), "network": "polygon"}
    out = x.verify_and_settle(p, reqs(), cfg=CFG,
                              _transport=mock_transport())
    assert out["settled"] is False and out["reason"] == "network_mismatch"


# --- PRX3 verify-then-settle + PRX4 tx hash ---------------------------------- #
def test_PRX3_happy_path_settles_with_tx_hash(monkeypatch):
    enabled(monkeypatch)
    out = x.verify_and_settle(good_payment(), reqs(), cfg=CFG,
                              _transport=mock_transport(tx="0xdeadbeef"))
    assert out["settled"] is True
    assert out["tx_hash"] == "0xdeadbeef"
    assert out["amount_atomic"] == "250000"


def test_PRX8_facilitator_payload_is_bound_to_advertised_resource(monkeypatch):
    enabled(monkeypatch)
    bodies = []

    def t(url, body):
        bodies.append(body)
        if url.endswith("/verify"):
            return {"isValid": True}
        return {"success": True, "transaction": "0xresource"}

    requirements = reqs()
    out = x.verify_and_settle(good_payment(), requirements, cfg=CFG,
                              _transport=t)
    assert out["settled"] is True
    assert len(bodies) == 2
    assert all(body["paymentPayload"]["resource"] ==
               requirements["resource"] for body in bodies)


def test_PRX8_conflicting_resource_refused_before_facilitator(monkeypatch):
    enabled(monkeypatch)
    payment = {**good_payment(), "resource": "https://attacker.invalid/free"}
    out = x.verify_and_settle(payment, reqs(), cfg=CFG,
                              _transport=lambda *_: pytest.fail(
                                  "facilitator must not be called"))
    assert out == {"settled": False, "reason": "resource_mismatch"}


def test_PRX3_verify_fail_never_settles(monkeypatch):
    enabled(monkeypatch)
    calls = []

    def t(url, body):
        calls.append(url)
        if url.endswith("/verify"):
            return {"isValid": False, "invalidReason": "bad_sig"}
        return {"success": True, "transaction": "0x1"}  # must NOT be reached
    out = x.verify_and_settle(good_payment(), reqs(), cfg=CFG, _transport=t)
    assert out["settled"] is False and "verify:bad_sig" in out["reason"]
    assert not any(u.endswith("/settle") for u in calls)   # PRX3: no settle


# --- PRX5 fail-closed -------------------------------------------------------- #
def test_PRX5_settle_failure_no_grant(monkeypatch):
    enabled(monkeypatch)
    out = x.verify_and_settle(good_payment(), reqs(), cfg=CFG,
                              _transport=mock_transport(settle_ok=False))
    assert out["settled"] is False and "settle:reverted" in out["reason"]


def test_PRX5_facilitator_exception_fails_closed(monkeypatch):
    enabled(monkeypatch)

    def boom(url, body):
        raise ConnectionError("facilitator down")
    out = x.verify_and_settle(good_payment(), reqs(), cfg=CFG, _transport=boom)
    assert out["settled"] is False and out["reason"].startswith("exception:")


def test_PRX5_malformed_header_returns_none():
    assert x.parse_payment_header(None) is None
    assert x.parse_payment_header("!!!not-base64!!!") is None
    assert x.parse_payment_header("") is None


def test_PRX5_settle_without_tx_hash_refused(monkeypatch):
    enabled(monkeypatch)

    def t(url, body):
        if url.endswith("/verify"):
            return {"isValid": True}
        return {"success": True}                     # no transaction field
    out = x.verify_and_settle(good_payment(), reqs(), cfg=CFG, _transport=t)
    assert out["settled"] is False and "no_tx_hash" in out["reason"]


def test_PRX5_disabled_settle_refuses(monkeypatch):
    monkeypatch.delenv("X402_ENABLED", raising=False)
    out = x.verify_and_settle(good_payment(), {"network": "base",
                                               "scheme": "exact"}, cfg=CFG,
                              _transport=mock_transport())
    assert out["settled"] is False and out["reason"] == "x402_disabled"


# --- header round-trip ------------------------------------------------------- #
def test_parse_payment_header_roundtrip():
    payload = good_payment()
    header = base64.b64encode(json.dumps(payload).encode()).decode()
    assert x.parse_payment_header(header) == payload


# --- CDP JWT auth (fixed 2026-07-18 per Sol's finding) ----------------------- #
def test_cdp_jwt_is_request_bound_ed25519_and_verifies():
    """A fresh Ed25519 JWT per request, bound to METHOD host+path, ~2min
    exp, and cryptographically verifiable against the key's public half."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey)
    seed = bytes(range(32))
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    pub = priv.public_key()
    secret_b64 = base64.b64encode(
        seed + pub.public_bytes_raw()).decode()      # 64-byte libsodium form
    key_id = "11111111-2222-3333-4444-555555555555"
    tok = x.cdp_jwt(key_id, secret_b64, "POST",
                    "api.cdp.coinbase.com", "/x402/verify")
    h_b64, c_b64, s_b64 = tok.split(".")

    def unpad(s):
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    header = json.loads(unpad(h_b64))
    claims = json.loads(unpad(c_b64))
    assert header["alg"] == "EdDSA" and header["kid"] == key_id
    assert claims["sub"] == key_id and claims["iss"] == "cdp"
    assert claims["uris"] == ["POST api.cdp.coinbase.com/x402/verify"]
    assert 100 <= claims["exp"] - claims["nbf"] <= 130      # ~2 min window
    # signature verifies against the public key over header.claims
    pub.verify(unpad(s_b64), f"{h_b64}.{c_b64}".encode())


def test_cdp_jwt_nonce_differs_per_call():
    seed = bytes(range(32))
    priv = Ed25519PrivateKey.from_private_bytes(seed) if False else None  # noqa
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey)
    pub = Ed25519PrivateKey.from_private_bytes(bytes(range(32))).public_key()
    secret = base64.b64encode(bytes(range(32)) + pub.public_bytes_raw()).decode()
    a = x.cdp_jwt("kid", secret, "POST", "h", "/p")
    b = x.cdp_jwt("kid", secret, "POST", "h", "/p")
    assert a != b                                    # fresh nonce each call


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
