"""CX1-CX7: Signed Cliff Check product invariants on the existing tax mount."""
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import sys
from types import SimpleNamespace
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from cliff_check import CliffCheckService
from payment_gate import GATE_ATTR, PRICE_MINOR, PaymentGate
from state_store import StateStore
from x402_http import (BUYER_FEEDBACK_VERSION, SETTLEMENT_CLASSIFICATION_VERSION,
                       make_buyer_feedback_route, settlement_metrics)

SPEC = json.loads((ROOT / "products/signed-cliff-check/sample_solar_48e.json").read_text())


def load_engine():
    spec = importlib.util.spec_from_file_location(
        "cliff_test_engine", ROOT / "taxcredit-engine-agent/src/__init__.py",
        submodule_search_locations=[str(ROOT / "taxcredit-engine-agent/src")])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.build()


def payload(facts=None, **extra):
    return {"action": "signed_cliff_check", "credit": "48E", "client": "Buyer",
            "project": "Roof", "facts": dict(SPEC["facts"] if facts is None else facts), **extra}


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIFF_CHECK_PARTNER_CODES", "PARTNER-ONE")
    engine = load_engine()
    svc = CliffCheckService(engine)
    store = StateStore(tmp_path / "state.sqlite3")
    store.attach("signed-cliff-check", svc)
    # The metering core is only needed for refused-call telemetry.
    meter_spec = importlib.util.spec_from_file_location(
        "cliff_test_meter", ROOT / "agent-metering-agent/src/__init__.py",
        submodule_search_locations=[str(ROOT / "agent-metering-agent/src")])
    meter_mod = importlib.util.module_from_spec(meter_spec)
    sys.modules[meter_spec.name] = meter_mod
    meter_spec.loader.exec_module(meter_mod)
    core_spec = importlib.util.spec_from_file_location("cliff_test_meter.core", ROOT / "agent-metering-agent/src/core.py")
    core_mod = importlib.util.module_from_spec(core_spec)
    sys.modules[core_spec.name] = core_mod
    core_spec.loader.exec_module(core_mod)
    meter = core_mod.build()
    store.attach("metering", meter)
    PaymentGate(store, meter).attach("signed-cliff-check", svc)
    return engine, svc, store


def call(svc, item):
    return asyncio.run(svc.process(item))


def test_cx1_all_report_money_is_engine_sourced(tmp_path, monkeypatch):
    engine, svc, store = setup(tmp_path, monkeypatch)
    try:
        receipt = call(svc, payload(partner_code="PARTNER-ONE"))["data"]["receipt"]
        direct = engine.calculate("48E", SPEC["facts"])
        assert receipt["result"]["credit_amount_usd"] == direct["credit_amount_usd"]
        for row in receipt["adder_upside"]:
            patch = {"Domestic content bonus": {"domestic_content_met": True},
                     "Energy community bonus": {"energy_community": True},
                     "Both adders": {"domestic_content_met": True,
                                     "energy_community": True}}[row["scenario"]]
            assert row["credit_amount_usd"] == engine.calculate(
                "48E", {**SPEC["facts"], **patch})["credit_amount_usd"]
    finally:
        store.close()


def test_cx2_indeterminate_is_free_and_lists_every_missing_fact(tmp_path, monkeypatch):
    _, svc, store = setup(tmp_path, monkeypatch)
    try:
        facts = dict(SPEC["facts"]); facts.pop("pwa_met"); facts.pop("energy_community")
        out = call(svc, payload(facts))
        assert out["status"] == "ok"
        assert out["data"]["receipt"]["calculation_status"] == "indeterminate"
        assert {"pwa_met", "energy_community"} <= set(out["data"]["missing_facts"])
        assert all(f in out["data"]["report_html"] for f in out["data"]["missing_facts"])
        gate = getattr(svc, GATE_ATTR)
        assert gate["used"] == gate["refused"] == 0
    finally:
        store.close()


def test_cx3_partner_code_three_uses_then_normal_price(tmp_path, monkeypatch):
    _, svc, store = setup(tmp_path, monkeypatch)
    try:
        for _ in range(3):
            assert call(svc, payload(partner_code="PARTNER-ONE"))["status"] == "ok"
        fourth = call(svc, payload(partner_code="PARTNER-ONE"))
        assert fourth["error_type"] == "payment_required"
        assert fourth["amount_minor"] == PRICE_MINOR["signed-cliff-check"] == 14900
        assert list(svc._partner_redemptions.values()) == [3]
        assert len(svc._partner_log) == 3
    finally:
        store.close()


def test_cx4_signature_and_engine_verification(tmp_path, monkeypatch):
    engine, svc, store = setup(tmp_path, monkeypatch)
    try:
        receipt = call(svc, payload(partner_code="PARTNER-ONE"))["data"]["receipt"]
        signature = receipt["signature"]
        assert hashlib.sha256((signature["salt"] + receipt["result"]["audit_sha256"]).encode()).hexdigest() == signature["commit_hash"]
        assert engine.verify_result(receipt["result"])["valid"] is True
    finally:
        store.close()


def test_cx5_transport_does_not_confirm_delivery_or_usefulness():
    record = {"surface": "http-402-v2",
              "classification_version": SETTLEMENT_CLASSIFICATION_VERSION,
              "self_settle": False, "route": "taxcredit-engine/signed_cliff_check",
              "amount_atomic": "149000000", "delivery_status": "delivered",
              "payer_wallet": "0xexternal", "timestamp": "2026-09-23T00:00:00Z"}
    state = {"signed-cliff-check": {"consumed_x402": {"one": record}}}
    before = settlement_metrics(state)["total"]
    assert before["external_paid_results_delivered"] == 0
    assert before["external_buyer_feedback_useful"] == 0
    record["buyer_feedback"] = {"version": BUYER_FEEDBACK_VERSION, "useful": True}
    after = settlement_metrics(state)["total"]
    assert after["external_paid_results_delivered"] == 1
    assert after["external_buyer_feedback_useful"] == 1
    record["self_settle"] = True
    internal = settlement_metrics(state)["total"]
    assert internal["external_paid_results_delivered"] == 0
    assert internal["external_buyer_feedback_useful"] == 0


def test_cx5_only_product_feedback_endpoint_confirms_paid_delivery(tmp_path, monkeypatch):
    _, svc, store = setup(tmp_path, monkeypatch)
    try:
        token = "buyer-feedback-token-with-enough-entropy-for-test"
        gate = getattr(svc, GATE_ATTR)
        gate["consumed_x402"]["paid"] = {
            "surface": "http-402-v2",
            "classification_version": SETTLEMENT_CLASSIFICATION_VERSION,
            "self_settle": False, "route": "taxcredit-engine/signed_cliff_check",
            "amount_atomic": "149000000", "delivery_status": "delivered",
            "payer_wallet": "0xexternal", "timestamp": "2026-09-23T00:00:00Z",
            "feedback_token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        }
        class Request:
            url = SimpleNamespace(path="/cliff-check/feedback")
            async def json(self):
                return {"feedback_token": token, "outcome": "NOT_USEFUL",
                        "would_buy_again": False, "note": "Missing adviser context",
                        "idempotency_key": "cliff-buyer-feedback-1"}
        handler = make_buyer_feedback_route({"signed-cliff-check": svc}, store)
        before = settlement_metrics({"signed-cliff-check": gate})["total"]
        assert before["external_paid_results_delivered"] == 0
        response = asyncio.run(handler(Request()))
        assert response.status_code == 201
        after = settlement_metrics({"signed-cliff-check": gate})["total"]
        assert after["external_paid_results_delivered"] == 1
        assert after["external_buyer_feedback_useful"] == 0
        assert gate["consumed_x402"]["paid"]["buyer_feedback"]["note"] == "Missing adviser context"
    finally:
        store.close()


def test_cx6_delivered_report_has_no_scripts_or_external_assets(tmp_path, monkeypatch):
    _, svc, store = setup(tmp_path, monkeypatch)
    try:
        page = call(svc, payload(partner_code="PARTNER-ONE"))["data"]["report_html"]
        assert "<script" not in page.lower()
        assert not re.search(r"(?:src|href)=[^>]+\.(?:css|js)(?:[\"']|\b)", page, re.I)
    finally:
        store.close()


def test_cx7_gateway_keeps_tax_mount_and_product_route():
    from viridis_mcp_gateway import MOUNTS
    from x402_http import X402_HTTP_TOOLS, route_price_minor
    assert "signed-cliff-check" not in MOUNTS
    assert X402_HTTP_TOOLS[("taxcredit-engine", "signed_cliff_check")] == "signed_cliff_check"
    assert route_price_minor("taxcredit-engine", "signed_cliff_check") == 14900
