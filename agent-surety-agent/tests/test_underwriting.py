"""agent-surety-agent — underwriting invariant tests (SB9–SB10, model uw-v1)."""
import asyncio

from src.core import (UW_CEILING_MULT_PPM, UW_UNKNOWN_MULT_PPM, build)


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def quote(a, coverage=100_000, days=30, **hist):
    return run(a.process({"action": "price_bond", "coverage_minor": coverage,
                          "duration_days": days, "history": hist}))


def test_sb9_deterministic_and_integer_only():
    a, b = build(), build()
    q1 = quote(a, attestations=3, successful_deliveries=5)["data"]
    q2 = quote(b, attestations=3, successful_deliveries=5)["data"]
    assert q1["premium_minor"] == q2["premium_minor"]
    assert q1["quote_hash"] == q2["quote_hash"]            # recomputable
    assert isinstance(q1["premium_minor"], int)
    assert isinstance(q1["multiplier_ppm"], int)
    # Different inputs => different hash (hash actually binds the quote).
    q3 = quote(build(), attestations=4, successful_deliveries=5)["data"]
    assert q3["quote_hash"] != q1["quote_hash"]


def test_sb9_pure_never_mutates_state():
    a = build()
    before = run(a.process({"action": "list"}))["data"]
    for _ in range(3):
        quote(a, slashes=1)
    after = run(a.process({"action": "list"}))["data"]
    assert before == after == {"count": 0, "bonds": []}


def test_sb9_risk_monotonicity():
    a = build()
    unknown = quote(a)["data"]["premium_minor"]
    proven = quote(a, attestations=10, successful_deliveries=20,
                   bonds_completed=4)["data"]["premium_minor"]
    slashed = quote(a, slashes=2)["data"]["premium_minor"]
    assert proven < unknown < slashed
    # Unknown counterparty pays the 3x spread.
    assert quote(a)["data"]["multiplier_ppm"] == UW_UNKNOWN_MULT_PPM
    # Longer coverage costs more; bigger coverage costs more.
    assert quote(a, days=90)["data"]["premium_minor"] > unknown
    assert quote(a, coverage=1_000_000)["data"]["premium_minor"] > unknown
    # Multiplier never exceeds the ceiling.
    worst = quote(a, slashes=3, slashed_minor=49_999)["data"]
    assert worst["multiplier_ppm"] <= UW_CEILING_MULT_PPM


def test_sb10_risk_ceiling_declines_never_quotes():
    a = build()
    d1 = quote(a, slashes=4)["data"]
    assert d1["decision"] == "declined" and "premium_minor" not in d1
    assert d1["quote_hash"]                                  # decline is signed too
    d2 = quote(a, slashed_minor=50_000)["data"]              # 50% of 100k coverage
    assert d2["decision"] == "declined"
    # Just under the ceiling still quotes.
    ok = quote(a, slashes=3, slashed_minor=49_999)["data"]
    assert ok["decision"] == "quote" and ok["premium_minor"] >= 1


def test_sb2_sb8_validation_envelopes():
    a = build()
    r = run(a.process({"action": "price_bond", "coverage_minor": 0,
                       "duration_days": 30}))
    assert r["status"] == "error" and r["field"] == "coverage_minor"
    r = run(a.process({"action": "price_bond", "coverage_minor": 100,
                       "duration_days": 400}))
    assert r["status"] == "error" and r["field"] == "duration_days"
    r = run(a.process({"action": "price_bond", "coverage_minor": 100,
                       "duration_days": 30, "history": {"slashes": -1}}))
    assert r["status"] == "error" and r["field"] == "history.slashes"
    r = run(a.process({"action": "price_bond", "coverage_minor": 100,
                       "duration_days": 30, "history": {"slashes": 1.5}}))
    assert r["status"] == "error"                            # SB2: no floats
