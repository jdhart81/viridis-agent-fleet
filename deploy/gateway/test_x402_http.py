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
    def __init__(self, agent, tool, headers=None, body=None, method="POST",
                 query=None):
        self.path_params = {"agent": agent, "tool": tool}
        self.headers = headers or {}
        self._body = body if body is not None else {}
        self.method = method
        self.query_params = query or {}

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
    assert a["scheme"] == "exact" and a["payTo"] == "0xViridis"
    assert a["outputSchema"] == {"type": "object",
                                  "additionalProperties": True}
    assert "MCP pointer: https://mcp.test/smartscale/mcp" in a["description"]


def test_H402_1_get_is_a_real_unpaid_discovery_challenge(rig):
    handler, _, _ = rig
    r = go(handler, FakeRequest("smartscale", "measure", method="GET"))
    assert r.status_code == 402
    assert body_of(r)["error"] == "X-PAYMENT required"


# --- H402-2 settle-then-serve + H402-4 ungated exec -------------------------- #
def test_H402_2_paid_settles_and_serves_the_tool(rig):
    handler, scale, _ = rig
    r = go(handler, req(headers={"x-payment": header()}))
    assert r.status_code == 200
    assert r.headers["X-Payment-Tx"] == "0xhttp1"
    assert body_of(r).get("status") in ("success", "ok")
    stored = next(iter(getattr(scale, GATE_ATTR)["consumed_x402"].values()))
    assert stored["delivery_status"] == "delivered"
    assert stored["delivery_recorded_at"].endswith("+00:00")


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


def test_wave8_health_exposes_per_route_and_total_buyer_signal(rig):
    _, scale, gate = rig
    getattr(scale, GATE_ATTR)["consumed_x402"]["v2:one"] = {
        "surface": "http-402-v2", "classification_version": 1,
        "route": "quantity-takeoff/calculate_takeoff",
        "payer_wallet": "0xExternal", "self_settle": False,
        "amount_atomic": "500000", "tx_hash": "0xfirst-dollar",
        "timestamp": "2026-07-20T01:02:03+00:00", "credits": 1,
    }
    telemetry = gate.status()["x402"]["http_settlement_telemetry"]
    assert telemetry["total"]["external_settlements"] == 1
    assert telemetry["total"]["distinct_external_payers"] == 1
    assert telemetry["total"]["repeat_external_purchases"] == 0
    assert telemetry["total"]["external_revenue_atomic"] == 500000
    assert telemetry["total"]["external_paid_results_delivered"] == 0
    assert telemetry["total"]["external_paid_results_failed"] == 0
    assert telemetry["total"]["external_paid_results_unknown"] == 1
    assert telemetry["total"]["first_external_settlement"] == {
        "tx_hash": "0xfirst-dollar",
        "timestamp": "2026-07-20T01:02:03+00:00"}
    assert telemetry["per_route"][
        "disclosure-compiler/compile_disclosure"][
            "first_external_settlement"] is None


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
    calls = []
    scale._gate_inner = lambda payload: calls.append(payload) or {"status": "ok"}
    r = go(handler, req(headers={"x-payment": header()}), settle=False)
    assert r.status_code == 402 and "settlement failed" in body_of(r)["error"]
    assert not getattr(scale, GATE_ATTR).get("consumed_x402")
    assert calls == []


def test_H402_7_malformed_header_402(rig):
    handler, _, _ = rig
    r = go(handler, req(headers={"x-payment": "!!!notb64!!!"}))
    assert r.status_code == 402 and "malformed" in body_of(r)["error"]


def test_H402_15_paid_tool_error_is_not_reported_as_delivered(rig):
    handler, scale, gate = rig

    def fail(_payload):
        raise RuntimeError("fixture failure")

    scale._gate_inner = fail
    r = go(handler, req(headers={"x-payment": header()}))
    assert r.status_code == 200
    assert body_of(r)["error_type"] == "tool_error"
    stored = next(iter(getattr(scale, GATE_ATTR)["consumed_x402"].values()))
    assert stored["delivery_status"] == "failed"
    telemetry = gate.status()["x402"]["http_settlement_telemetry"]["total"]
    # Legacy v1 settlements remain outside externally classified telemetry.
    assert telemetry["settlements_total"] == 0


def test_registered_production_allowlist_has_ten_priced_front_doors():
    expected = {
        ("taxcredit-engine", "signed_cliff_check"): "signed_cliff_check",
        ("regulatory-radar", "scan_regulations"): "scan",
        ("regulatory-radar", "monitor_changes"): "monitor_changes",
        ("taxcredit-engine", "calculate_tax_credit"): "calculate",
        ("ghg-ledger", "calculate_inventory"): "calculate_inventory",
        ("quantity-takeoff", "calculate_takeoff"): "calculate_takeoff",
        ("disclosure-compiler", "compile_disclosure"): "compile_disclosure",
        ("hive", "solve"): "solve",
        ("security-preflight", "security_preflight"): "scan",
        ("security-preflight", "scan_source"): "scan_source",
        ("security-preflight", "screen_injection"): "screen_injection",
    }

    import os
    for flag, route, action in [("MAXWELL_FLEET_ENABLED", ("maxwell-defense","rehearse_defense"), "rehearse_defense"), ("WU_WEI_FLEET_ENABLED", ("wu-wei-router","plan_workload"), "plan_workload")]:
        if os.environ.get(flag)=="1": expected[route]=action
    assert x402_http.X402_HTTP_TOOLS == expected


def test_agent402_has_a_fixed_price_regulatory_radar_alias():
    assert x402_http.AGENT402_HTTP_TOOLS == {
        ("regulatory-radar", "scan_regulations_agent402"): "scan",
    }
    assert x402_http.AGENT402_FIXED_ROUTE in x402_http.INTRO_EXEMPT_ROUTES
    assert x402_http.HIVE_FIXED_ROUTE in x402_http.INTRO_EXEMPT_ROUTES
    assert (
        x402_http.X402_HTTP_METADATA[
            x402_http.AGENT402_FIXED_ROUTE]["icon_url"]
        == "https://mcp.viridisconservation.com/brand/viridis-mark.svg")


def test_discovery_inventory_has_exact_prices_and_atomic_math():
    entries = {
        (e["agent"], e["tool"]): e
        for e in x402_http.discovery_entries("https://mcp.test")}
    assert len(entries) == len(x402_http.X402_HTTP_TOOLS)
    assert entries[("regulatory-radar", "scan_regulations")][
        "price_minor"] == 25
    assert entries[("regulatory-radar", "scan_regulations")][
        "amount_atomic_usdc"] == "250000"
    assert entries[("regulatory-radar", "monitor_changes")][
        "price_minor"] == 25
    assert entries[("regulatory-radar", "monitor_changes")][
        "amount_atomic_usdc"] == "250000"
    assert entries[("taxcredit-engine", "calculate_tax_credit")][
        "price_minor"] == 200
    assert entries[("taxcredit-engine", "calculate_tax_credit")][
        "amount_atomic_usdc"] == "2000000"
    assert entries[("taxcredit-engine", "signed_cliff_check")][
        "amount_atomic_usdc"] == "149000000"
    assert entries[("ghg-ledger", "calculate_inventory")][
        "price_minor"] == 100
    assert entries[("ghg-ledger", "calculate_inventory")][
        "amount_atomic_usdc"] == "1000000"
    assert entries[("quantity-takeoff", "calculate_takeoff")][
        "price_minor"] == 50
    assert entries[("quantity-takeoff", "calculate_takeoff")][
        "amount_atomic_usdc"] == "500000"
    assert entries[("disclosure-compiler", "compile_disclosure")][
        "price_minor"] == 200
    assert entries[("disclosure-compiler", "compile_disclosure")][
        "amount_atomic_usdc"] == "2000000"
    assert entries[("hive", "solve")]["price_minor"] == 500
    assert entries[("hive", "solve")][
        "amount_atomic_usdc"] == "5000000"
    assert entries[("security-preflight", "security_preflight")][
        "price_minor"] == 100
    assert entries[("security-preflight", "security_preflight")][
        "amount_atomic_usdc"] == "1000000"
    assert all(e["methods"] == ["GET", "POST"] for e in entries.values())
    live_routes = {
        f"{agent}/{tool}" for agent, tool in x402_http.X402_HTTP_TOOLS}
    for entry in entries.values():
        if entry["agent"] not in {"maxwell-defense", "wu-wei-router"} and entry["tool"] != "signed_cliff_check":
            assert entry["next_paid_routes"]
        for offer in entry["next_paid_routes"]:
            route = f"{offer['agent']}/{offer['tool']}"
            assert route in live_routes
            assert offer["method"] == "POST"
            assert offer["endpoint"] == f"https://mcp.test/x402/{route}"
            assert offer["mcp_endpoint"] == (
                f"https://mcp.test/{offer['agent']}/mcp")
            assert offer["amount_atomic_usdc"] == x402_rail.price_atomic(
                offer["price_minor"])
            metadata = x402_http.X402_HTTP_METADATA[
                (offer["agent"], offer["tool"])]
            assert offer["description"] == metadata["description"]
            assert offer["input_schema"] == metadata["input_schema"]
            assert offer["input_example"] == metadata["input_example"]
            assert offer["required_buyer_inputs"] == list(
                metadata["input_schema"].get("required", []))
            assert offer["quote"] == {
                "preflight_required": True,
                "authoritative_source": "next_route_unpaid_http_402",
                "payer_hint_header": "X402-Payer-Address",
                "payer_hint_value_source":
                    "caller_public_signing_address",
                "payer_hint_required_for_exact_quote":
                    (offer["agent"], offer["tool"])
                    not in x402_http.INTRO_EXEMPT_ROUTES,
                "payer_hint_authorizes_payment": False,
                "advertised_price_posture": "returning_payer_list_price",
            }


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
