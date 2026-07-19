#!/usr/bin/env python3
"""
H402-1..7 — the x402-native HTTP-402 surface, against a mock facilitator and
the real smartscale core + StateStore (smartscale is import-isolation-clean,
matching test_x402_gate.py). The tool allowlist is injected so this exercises
the exact handler logic without loading a submoduled agent. One test/claim.

Run:  pytest deploy/gateway/test_x402_http.py -q
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

import x402_rail                                             # noqa: E402
import x402_http                                             # noqa: E402
from payment_gate import PaymentGate, GATE_ATTR              # noqa: E402
from state_store import StateStore                           # noqa: E402


def _load(agent_dir):
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


SMARTSCALE = _load("smartscale-agent")
METERING = _load("agent-metering-agent")

# Inject a smartscale allowlist for the test (measure tool -> core action).
TEST_TOOLS = {("smartscale", "measure"): "measure_from_credit_card"}
MEASURE_ARGS = {"image_id": "img-1", "credit_card_pixel_width": 856.0,
                "objects": [{"label": "box", "pixel_width": 428.0,
                             "pixel_height": 214.0}]}


class FakeRequest:
    def __init__(self, agent, tool, headers=None, body=None):
        self.path_params = {"agent": agent, "tool": tool}
        self.headers = headers or {}
        self._body = body if body is not None else {}

    async def json(self):
        return self._body


def arm(monkeypatch):
    monkeypatch.setenv("X402_ENABLED", "1")
    monkeypatch.setenv("VIRIDIS_X402_ADDRESS", "0xViridis")
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://fac.test")


def header(nonce="n1"):
    return base64.b64encode(json.dumps(
        {"x402Version": 1, "scheme": "exact", "network": "base",
         "payload": {"nonce": nonce}}).encode()).decode()


def build(tmp_path, tools=TEST_TOOLS):
    store = StateStore(str(tmp_path / "s.db"))
    scale = SMARTSCALE.SmartScaleCore()
    meter = METERING.build()
    store.attach("smartscale", scale)
    gate = PaymentGate(store, meter, free_calls_per_day=10)
    gate.attach("smartscale", scale)             # sets _gate_inner
    cores = {"smartscale": scale}
    handler = x402_http.make_x402_http_route(
        cores, store, "https://mcp.test", tools=tools)
    return handler, scale, gate


def go(handler, req, settle=True, tx="0xhttp1"):
    orig = x402_rail.verify_and_settle
    x402_rail.verify_and_settle = lambda p, r, **k: (
        {"settled": True, "tx_hash": tx, "network": "base",
         "amount_atomic": r["maxAmountRequired"]} if settle
        else {"settled": False, "reason": "reverted"})
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(handler(req))
        finally:
            loop.close()
    finally:
        x402_rail.verify_and_settle = orig


def body_of(resp):
    return json.loads(resp.body.decode())


def req(headers=None, body=None):
    return FakeRequest("smartscale", "measure", headers=headers,
                       body=body if body is not None else MEASURE_ARGS)


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    arm(monkeypatch)
    return build(tmp_path)


# --- H402-1 real 402 --------------------------------------------------------- #
def test_H402_1_unpaid_returns_402_with_accepts(rig):
    handler, _, _ = rig
    r = go(handler, req())
    assert r.status_code == 402
    a = body_of(r)["accepts"][0]
    assert a["network"] == "base" and a["maxAmountRequired"] == "500000"  # 50c


# --- H402-2 settle-then-serve + H402-4 ungated exec -------------------------- #
def test_H402_2_paid_settles_and_serves_the_tool(rig):
    handler, _, _ = rig
    r = go(handler, req(headers={"x-payment": header()}))
    assert r.status_code == 200
    assert r.headers["X-Payment-Tx"] == "0xhttp1"
    assert body_of(r).get("status") in ("success", "ok")


# --- H402-3 exactly-once ----------------------------------------------------- #
def test_H402_3_replayed_payment_serves_nothing(rig):
    handler, scale, _ = rig
    h = header(nonce="same")
    assert go(handler, req(headers={"x-payment": h}), tx="0xA").status_code == 200
    b = go(handler, req(headers={"x-payment": h}), tx="0xB")
    assert b.status_code == 402 and "consumed" in body_of(b)["error"]
    assert len(getattr(scale, GATE_ATTR)["consumed_x402"]) == 1


# --- H402-5 unified telemetry ------------------------------------------------ #
def test_H402_5_settlement_shows_in_gate_status(rig):
    handler, _, gate = rig
    go(handler, req(headers={"x-payment": header()}), tx="0xTEL")
    s = gate.status()["x402"]["settled"]["smartscale"]
    assert s["payments"] == 1 and "0xTEL" in s["tx_hashes"]


# --- H402-6 allowlist / disabled --------------------------------------------- #
def test_H402_6_unknown_tool_is_404(rig):
    handler, _, _ = rig
    r = go(handler, FakeRequest("smartscale", "not_a_tool"))
    assert r.status_code == 404


def test_H402_6_disabled_rail_is_503(tmp_path, monkeypatch):
    monkeypatch.delenv("X402_ENABLED", raising=False)
    handler, _, _ = build(tmp_path)
    r = go(handler, req())
    assert r.status_code == 503


# --- H402-7 fail-closed ------------------------------------------------------ #
def test_H402_7_failed_settlement_serves_nothing(rig):
    handler, scale, _ = rig
    r = go(handler, req(headers={"x-payment": header()}), settle=False)
    assert r.status_code == 402 and "settlement failed" in body_of(r)["error"]
    assert not getattr(scale, GATE_ATTR).get("consumed_x402")


def test_H402_7_malformed_header_402(rig):
    handler, _, _ = rig
    r = go(handler, req(headers={"x-payment": "!!!notb64!!!"}))
    assert r.status_code == 402 and "malformed" in body_of(r)["error"]


def test_registered_production_allowlist_is_regulatory_radar():
    # the shipped default registry stays as intended (no test leakage)
    assert x402_http.X402_HTTP_TOOLS.get(
        ("regulatory-radar", "scan_regulations")) == "scan"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
