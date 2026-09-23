"""Tests for reconciliation.py — one per RV invariant (G10)."""
import asyncio
import copy
import importlib.util
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import reconciliation                                     # noqa: E402


def _load_metering():
    for m in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
    ps = importlib.util.spec_from_file_location(
        "src", ROOT / "agent-metering-agent" / "src" / "__init__.py",
        submodule_search_locations=[str(ROOT / "agent-metering-agent" / "src")])
    pkg = importlib.util.module_from_spec(ps)
    sys.modules["src"] = pkg
    ps.loader.exec_module(pkg)
    cs = importlib.util.spec_from_file_location(
        "src.core", ROOT / "agent-metering-agent" / "src" / "core.py")
    mod = importlib.util.module_from_spec(cs)
    sys.modules["src.core"] = mod
    cs.loader.exec_module(mod)
    return mod


METERING = _load_metering()
NOW = int(time.time())


class FakeCore:
    def __init__(self, state):
        self._payment_gate_state = state


class FakeGate:
    def __init__(self, cores):
        self._cores = cores


def _rig():
    meter = METERING.build()

    async def seed():
        gw = (await meter.process({
            "action": "create_meter", "_origin": "gateway",
            "provider": "viridis:taxcredit-engine",
            "consumer": "public-free-tier", "unit": "call",
            "price_minor_per_unit": 200}))["data"]["meter_id"]
        for i in range(3):
            await meter.process({"action": "record_usage", "meter_id": gw,
                                 "event_id": f"e{i}", "quantity": 1,
                                 "_origin": "gateway",
                                 "consumer_class": "external"})
        # Synthetic sandbox meter: must NOT pollute the ledger side (RV5).
        pub = (await meter.process({
            "action": "create_meter", "provider": "us", "consumer": "acme-corp",
            "unit": "call", "price_minor_per_unit": 999}))["data"]["meter_id"]
        await meter.process({"action": "record_usage", "meter_id": pub,
                             "event_id": "noise", "quantity": 7})
    asyncio.run(seed())
    gate = FakeGate({"taxcredit-engine": FakeCore({
        "invoices": [{"amount_minor": 600, "day": "2026-07-13"}],
        "redeemed_sessions": {"cs_live_A": {"credits": 3, "amount_minor": 600,
                                            "redeemed_at": "2026-07-13T10:00:00Z"}},
        "credits": 1,
    })})
    return meter, gate


def _stripe_ok(**kw):
    def fake(created_after_epoch=None, limit=100):
        return {"status": "ok", "has_more": False, "sessions": [
            {"session_id": "cs_live_A", "payment_status": "paid",
             "amount_total": 600, "currency": "usd",
             "created": NOW - 100, "livemode": True, "mode": "payment"},
            {"session_id": "cs_live_B", "payment_status": "paid",
             "amount_total": 400, "currency": "usd",
             "created": NOW - 50, "livemode": True, "mode": "payment"},
            {"session_id": "cs_test_C", "payment_status": "paid",
             "amount_total": 123, "currency": "usd",
             "created": NOW - 10, "livemode": False, "mode": "payment"},
        ]}
    return fake


def test_RV2_distinct_honest_numbers():
    meter, gate = _rig()
    rep = asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=_stripe_ok(), now_epoch=NOW))
    assert rep["status"] == "ok"
    ledger = rep["ledger"]["providers"]["viridis:taxcredit-engine"]
    assert ledger["gross_usage_value_minor"] == 600     # 3 calls x $2
    assert ledger["invoiced_minor"] == 600
    assert "us" not in rep["ledger"]["providers"]       # RV5: sandbox excluded
    assert rep["stripe"]["settled_minor"] == 1000       # live paid only
    assert rep["redemptions"]["total_redeemed_minor"] == 600
    assert rep["redemptions"]["by_agent"]["taxcredit-engine"]["credits_outstanding"] == 1
    # The numbers are reported side by side, never netted (RV2).
    assert set(rep["definitions"]) == {"gross_usage_value_minor",
                                       "invoiced_minor", "settled_minor",
                                       "redeemed_minor",
                                       "escrow_settled_minor",
                                       "connect_rail.transfers",
                                       "connect_rail.refunds"}


def test_RV3_discrepancies_enumerated():
    meter, gate = _rig()
    rep = asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=_stripe_ok(), now_epoch=NOW))
    kinds = {(d["type"], d.get("session_id")) for d in rep["discrepancies"]}
    assert ("paid_not_redeemed", "cs_live_B") in kinds
    assert rep["stripe"]["testmode_sessions"] == ["cs_test_C"]


def test_RV1_read_only():
    meter, gate = _rig()
    before_meters = copy.deepcopy(
        asyncio.run(meter.process({"action": "list_meters"})))
    before_gate = copy.deepcopy(
        gate._cores["taxcredit-engine"]._payment_gate_state)
    asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=_stripe_ok(), now_epoch=NOW))
    after_meters = asyncio.run(meter.process({"action": "list_meters"}))
    assert before_meters["data"] == after_meters["data"]
    assert before_gate == gate._cores["taxcredit-engine"]._payment_gate_state


def test_RV4_stripe_failure_degrades_structurally():
    meter, gate = _rig()

    def boom(**kw):
        raise RuntimeError("stripe down")
    rep = asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=boom, now_epoch=NOW))
    assert rep["status"] == "ok"                         # never an exception
    assert rep["stripe"]["status"] == "error"
    assert rep["ledger"]["totals"]["gross_usage_value_minor"] == 600

    def no_key(**kw):
        return {"status": "error", "error_type": "no_api_key", "message": "x"}
    rep2 = asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=no_key, now_epoch=NOW))
    assert rep2["stripe"]["status"] == "error"


def test_RV_validation():
    meter, gate = _rig()
    rep = asyncio.run(reconciliation.build_report(
        meter, gate, days=0, list_sessions=_stripe_ok(), now_epoch=NOW))
    assert rep["status"] == "error"


def test_RV6_escrow_settlement_is_non_cash_and_never_in_settled():
    """RV6: without custody evidence, a2a escrow consumption is entirely
    internal-ledger, and settled_minor (Stripe cash) is unchanged by it."""
    meter, gate = _rig()
    gate._cores["taxcredit-engine"]._payment_gate_state["consumed_escrows"] = {
        "esc_000042": {"credits": 2, "amount_minor": 400,
                       "consumed_at": "2026-07-16T04:00:00Z"}}
    rep = asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=_stripe_ok(), now_epoch=NOW))
    a2a = rep["a2a_escrow"]
    assert a2a["cash_minor"] == 0                     # no custody registry
    assert a2a["internal_ledger_minor"] == 400
    assert "NOT cash" in a2a["meaning"]
    assert a2a["total_escrow_settled_minor"] == 400
    assert a2a["by_agent"]["taxcredit-engine"]["escrows_consumed"] == 1
    assert a2a["by_agent"]["taxcredit-engine"]["credits_granted"] == 2
    # Cash number identical to a run with no escrow consumption:
    assert rep["stripe"]["settled_minor"] == 1000
    assert rep["redemptions"]["total_redeemed_minor"] == 600
    assert "NOT" in rep["definitions"]["escrow_settled_minor"] \
        or "not" in rep["definitions"]["escrow_settled_minor"]


def test_RV6_custody_registry_splits_cash_from_internal():
    """PG17: an escrow in the custody registry counts as cash (a labeled
    subset of settled_minor, never added to it); its funding session is not
    a paid_not_redeemed discrepancy; unregistered escrows stay internal."""
    class FakeCustodyState:
        def __init__(self):
            # cs_live_B (a real paid session in _stripe_ok) funded esc_cash.
            self.funded = {"esc_cash": {"session_id": "cs_live_B",
                                        "amount_total": 400,
                                        "livemode": True,
                                        "funded_at": "2026-07-16T05:00:00Z"}}

    class FakeCustody:
        state = FakeCustodyState()
        def status(self):
            return {"cash_funded_escrows": 1, "cash_funded_minor": 400}

    meter, gate = _rig()
    gate._cores["taxcredit-engine"]._payment_gate_state["consumed_escrows"] = {
        "esc_cash": {"credits": 2, "amount_minor": 400,
                     "consumed_at": "2026-07-16T05:10:00Z"},
        "esc_internal": {"credits": 1, "amount_minor": 200,
                         "consumed_at": "2026-07-16T05:11:00Z"}}
    rep = asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=_stripe_ok(), now_epoch=NOW,
        custody=FakeCustody()))
    a2a = rep["a2a_escrow"]
    assert a2a["cash_minor"] == 400
    assert a2a["internal_ledger_minor"] == 200
    assert a2a["by_agent"]["taxcredit-engine"]["cash_minor"] == 400
    assert rep["stripe"]["settled_minor"] == 1000     # subset, never added
    kinds = {(d["type"], d.get("session_id")) for d in rep["discrepancies"]}
    assert ("paid_not_redeemed", "cs_live_B") not in kinds  # escrow, not credits
    assert a2a["custody"]["cash_funded_minor"] == 400


# --- RV7: Connect-rail outflows (2026-07-19) --------------------------------- #
class FakeConnectState:
    def __init__(self, transfers):
        self.transfers = transfers


class FakeConnect:
    def __init__(self, transfers):
        self.state = FakeConnectState(transfers)


def test_RV7_transfers_and_refunds_reported_and_grouped():
    """Connect transfers are summed and grouped by transfer_group (the
    originating escrow/bond id); custody refund_id instructions are summed
    as refunds. Neither touches settled_minor/redeemed_minor/a2a_escrow."""
    class FakeCustodyState:
        def __init__(self):
            self.funded = {}
            self.instructions = {
                "esc_refunded": {"type": "refund", "scope": "same_party_refund",
                                 "refund_id": "re_123", "refund_minor": 150,
                                 "executed": True},
                "esc_payout": {"type": "payout", "rail": "manual",
                               "executed": False},   # no refund_id: not a refund
            }

    class FakeCustody:
        state = FakeCustodyState()
        def status(self):
            return {"cash_funded_escrows": 0, "cash_funded_minor": 0}

    connect = FakeConnect({
        "escrow-payout:esc_1": {"amount_minor": 300, "transfer_group": "esc_1",
                                "payee_id": "p1", "transfer_id": "tr_1"},
        "bond-slash:bond_1:c1": {"amount_minor": 500, "transfer_group": "bond_1",
                                 "payee_id": "claimant-1", "transfer_id": "tr_2"},
        "bond-slash:bond_1:c2": {"amount_minor": 250, "transfer_group": "bond_1",
                                 "payee_id": "claimant-2", "transfer_id": "tr_3"},
    })
    meter, gate = _rig()
    rep = asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=_stripe_ok(), now_epoch=NOW,
        custody=FakeCustody(), connect=connect))
    cr = rep["connect_rail"]
    assert cr["transfers"]["total_minor"] == 300 + 500 + 250
    assert cr["transfers"]["count"] == 3
    assert cr["transfers"]["by_group"]["esc_1"]["transfers_minor"] == 300
    assert cr["transfers"]["by_group"]["esc_1"]["count"] == 1
    assert cr["transfers"]["by_group"]["bond_1"]["transfers_minor"] == 750
    assert cr["transfers"]["by_group"]["bond_1"]["count"] == 2
    assert cr["refunds"]["total_minor"] == 150
    assert cr["refunds"]["count"] == 1
    # Untouched: cash/redemption numbers identical to a run with no rail.
    assert rep["stripe"]["settled_minor"] == 1000
    assert rep["redemptions"]["total_redeemed_minor"] == 600
    assert rep["a2a_escrow"]["cash_minor"] == 0
    assert "connect_rail.transfers" in rep["definitions"]
    assert "connect_rail.refunds" in rep["definitions"]


def test_RV7_empty_bucket_without_connect_or_refunds():
    """No connect object, and custody with no refund_id instructions:
    the bucket still renders, empty, never a crash (RV4 posture)."""
    meter, gate = _rig()
    rep = asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=_stripe_ok(), now_epoch=NOW))
    cr = rep["connect_rail"]
    assert cr["transfers"]["total_minor"] == 0
    assert cr["transfers"]["count"] == 0
    assert cr["transfers"]["by_group"] == {}
    assert cr["refunds"]["total_minor"] == 0
    assert cr["refunds"]["count"] == 0

    class FakeCustodyState:
        def __init__(self):
            self.funded = {}
            self.instructions = {"esc_x": {"type": "payout", "rail": "manual",
                                           "executed": False}}

    class FakeCustody:
        state = FakeCustodyState()
        def status(self):
            return {"cash_funded_escrows": 0, "cash_funded_minor": 0}

    rep2 = asyncio.run(reconciliation.build_report(
        meter, gate, days=30, list_sessions=_stripe_ok(), now_epoch=NOW,
        custody=FakeCustody()))
    assert rep2["connect_rail"]["refunds"]["count"] == 0
