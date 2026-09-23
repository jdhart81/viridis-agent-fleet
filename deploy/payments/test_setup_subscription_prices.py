"""Tests for setup_subscription_prices.py — one per SP invariant."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from setup_subscription_prices import (build_catalog, ensure_price,  # noqa: E402
                                       find_existing_price)

PLAN = {"id": "climate-seat", "name": "Climate Seat", "price_minor": 14900,
        "interval": "month", "covered_agents": ["disclosure-compiler", "ghg-ledger"]}


def _transport_with(prices):
    calls = []

    def fake(method, path, key, params=None):
        calls.append((method, path, dict(params or {})))
        if method == "GET" and path == "prices":
            return {"data": prices}
        if method == "POST" and path == "products":
            return {"id": "prod_test1"}
        if method == "POST" and path == "prices":
            return {"id": "price_new1"}
        raise AssertionError(f"unexpected {method} {path}")
    fake.calls = calls
    return fake


def test_SP2_existing_price_reused_never_duplicated():
    existing = [{"id": "price_live_A", "unit_amount": 14900, "currency": "usd",
                 "recurring": {"interval": "month"},
                 "metadata": {"viridis_plan_id": "climate-seat"}}]
    t = _transport_with(existing)
    pid, how = ensure_price("k", PLAN, "usd", apply=True, _req=t)
    assert pid == "price_live_A" and how == "reused"
    assert all(m == "GET" for m, _, _ in t.calls)      # zero mutations
    # Amount mismatch => NOT reused (price change means a new Price).
    stale = [dict(existing[0], unit_amount=9900)]
    assert find_existing_price("k", PLAN, "usd", _req=_transport_with(stale)) is None


def test_SP1_dry_run_never_mutates():
    t = _transport_with([])
    pid, how = ensure_price("k", PLAN, "usd", apply=False, _req=t)
    assert pid is None and "dry-run" in how
    assert all(m == "GET" for m, _, _ in t.calls)


def test_SP1_apply_creates_product_then_price():
    t = _transport_with([])
    pid, how = ensure_price("k", PLAN, "usd", apply=True, _req=t)
    assert pid == "price_new1" and how == "created"
    posts = [(m, p) for m, p, _ in t.calls if m == "POST"]
    assert posts == [("POST", "products"), ("POST", "prices")]


def test_SP3_SP4_catalog_transform_is_minimal_and_gated():
    catalog = {"pack_version": "0.2.0", "effective_as_of": "2026-07-13",
               "currency": "usd", "lifecycle_policy": {"x": 1},
               "plans": [{"id": "climate-seat", "price_minor": 14900,
                          "interval": "month", "stripe_price_id": None,
                          "approval_status": "draft", "checkout_enabled": False,
                          "included_calls_per_month": 1000}]}
    out = build_catalog(catalog, {"climate-seat": "price_X"}, approve=False)
    p = out["plans"][0]
    assert p["stripe_price_id"] == "price_X"
    assert p["approval_status"] == "draft" and p["checkout_enabled"] is False  # SP4
    assert p["price_minor"] == 14900 and p["included_calls_per_month"] == 1000  # SP3
    assert out["lifecycle_policy"] == {"x": 1}
    assert out["pack_version"] == "0.3.0"
    approved = build_catalog(catalog, {"climate-seat": "price_X"}, approve=True)
    assert approved["plans"][0]["checkout_enabled"] is True
    # Plans without a price id never get approved flags flipped.
    none = build_catalog(catalog, {}, approve=True)
    assert none["plans"][0]["checkout_enabled"] is False
    # Input catalog untouched (deep copy).
    assert catalog["plans"][0]["stripe_price_id"] is None
