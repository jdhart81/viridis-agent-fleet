#!/usr/bin/env python3
"""
PRX end-to-end through the REAL gate: an X-PAYMENT header past the free tier
settles via a mocked facilitator and grants a credit that serves the call.
Uses the real smartscale + metering cores + StateStore.

Run:  pytest deploy/gateway/test_x402_gate.py -q
"""
import asyncio
import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import x402_rail                                            # noqa: E402
from payment_gate import PaymentGate, GATE_ATTR             # noqa: E402
from request_context import request_context                # noqa: E402
from state_store import StateStore                          # noqa: E402


def _load_pkg(agent_dir):
    for m in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
    ps = importlib.util.spec_from_file_location(
        "src", ROOT / agent_dir / "src" / "__init__.py",
        submodule_search_locations=[str(ROOT / agent_dir / "src")])
    pkg = importlib.util.module_from_spec(ps)
    sys.modules["src"] = pkg
    ps.loader.exec_module(pkg)
    cs = importlib.util.spec_from_file_location(
        "src.core", ROOT / agent_dir / "src" / "core.py")
    mod = importlib.util.module_from_spec(cs)
    sys.modules["src.core"] = mod
    cs.loader.exec_module(mod)
    return mod


SMARTSCALE = _load_pkg("smartscale-agent")
METERING = _load_pkg("agent-metering-agent")

CALL = {"action": "measure_from_credit_card", "image_id": "img-1",
        "credit_card_pixel_width": 856.0,
        "objects": [{"label": "box", "pixel_width": 428.0,
                     "pixel_height": 214.0}]}


def arm(monkeypatch):
    monkeypatch.setenv("X402_ENABLED", "1")
    monkeypatch.setenv("VIRIDIS_X402_ADDRESS", "0xViridis")
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://fac.test")


def payment_header(nonce="n1"):
    payload = {"x402Version": 1, "scheme": "exact", "network": "base",
               "payload": {"signature": "0x", "nonce": nonce}}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def build(db, free=0):
    store = StateStore(db)
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    store.attach("smartscale", scale)
    store.attach("metering", meter)
    gate = PaymentGate(store, meter, free_calls_per_day=free)
    gate.attach("smartscale", scale)
    return store, gate, scale


def call(core, header=None, tx="0xtx1"):
    # patch the module verify_and_settle to a mock (settles successfully)
    orig = x402_rail.verify_and_settle
    x402_rail.verify_and_settle = lambda p, r, **k: {
        "settled": True, "tx_hash": tx, "network": "base",
        "amount_atomic": r["maxAmountRequired"]}
    try:
        ctx = {"consumer_class": "external", "channel": "script",
               "caller": "ext:payer", "is_test": False, "x402_payment": header}
        with request_context(ctx):
            result = core.process(dict(CALL))
        if asyncio.iscoroutine(result):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(result)
            finally:
                loop.close()
        return result
    finally:
        x402_rail.verify_and_settle = orig


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


def test_PRX_x402_payment_serves_the_call(monkeypatch, db):
    arm(monkeypatch)
    _, gate, scale = build(db, free=0)          # zero free tier
    out = call(scale, header=payment_header())
    assert out["status"] == "ok"                # settled -> credit -> served
    g = getattr(scale, GATE_ATTR)
    assert len(g["consumed_x402"]) == 1
    tx = next(iter(g["consumed_x402"].values()))["tx_hash"]
    assert tx == "0xtx1"


def test_PRX_no_header_still_refused(monkeypatch, db):
    arm(monkeypatch)
    _, gate, scale = build(db, free=0)
    out = call(scale, header=None)              # no x402 payment
    assert out["error_type"] == "payment_required"


def test_PRX_replayed_header_grants_once(monkeypatch, db):
    """PRX4: the same X-PAYMENT settles once; a replay never double-credits."""
    arm(monkeypatch)
    _, gate, scale = build(db, free=0)
    h = payment_header(nonce="same")
    assert call(scale, header=h, tx="0xA")["status"] == "ok"
    g = getattr(scale, GATE_ATTR)
    # replay same header: idempotent no-op, no new settlement, and with no
    # fresh credit the call is refused (proves it didn't re-grant).
    out2 = call(scale, header=h, tx="0xB")
    assert out2["error_type"] == "payment_required"
    assert len(g["consumed_x402"]) == 1
    assert next(iter(g["consumed_x402"].values()))["tx_hash"] == "0xA"


def test_PRX_disabled_ignores_header(monkeypatch, db):
    monkeypatch.delenv("X402_ENABLED", raising=False)
    _, gate, scale = build(db, free=0)
    out = call(scale, header=payment_header())
    assert out["error_type"] == "payment_required"   # rail off -> no settle
    assert not getattr(scale, GATE_ATTR).get("consumed_x402")


def test_PRX_status_reports_x402_rail(monkeypatch, db):
    arm(monkeypatch)
    _, gate, scale = build(db, free=0)
    call(scale, header=payment_header(), tx="0xST")
    s = gate.status()
    assert s["x402"]["enabled"] is True
    assert s["x402"]["settled"]["smartscale"]["payments"] == 1
    assert "0xST" in s["x402"]["settled"]["smartscale"]["tx_hashes"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
