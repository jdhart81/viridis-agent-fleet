#!/usr/bin/env python3
"""
Tests for weave.py (WV1-WV8) — real offset-clearinghouse core, real
StateStore. Same-account allocations (EnergyAI -> Viridis Conservation,
both under Stripe acct_1BLyFZDTpwaqE8Ss) execute autonomously (revised
2026-07-19); the ledger is asserted to be an obligation ledger, never
fleet revenue. External restoration payees use the same Connect dual-rail
pattern as escrow custody: onboarded payees auto-execute; non-onboarded
payees receive the certified fallback.

Run:  pytest deploy/gateway/test_weave.py -q
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from weave import Weave, RATE_SCHEDULE          # noqa: E402
from state_store import StateStore              # noqa: E402


def _load_offsets():
    for m in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[m]
    d = ROOT / "agent-offset-clearinghouse-agent"
    ps = importlib.util.spec_from_file_location(
        "src", d / "src" / "__init__.py",
        submodule_search_locations=[str(d / "src")])
    pkg = importlib.util.module_from_spec(ps)
    sys.modules["src"] = pkg
    ps.loader.exec_module(pkg)
    cs = importlib.util.spec_from_file_location("src.core", d / "src" / "core.py")
    mod = importlib.util.module_from_spec(cs)
    sys.modules["src.core"] = mod
    cs.loader.exec_module(mod)
    modules = {m: sys.modules[m] for m in list(sys.modules)
               if m == "src" or m.startswith("src.")}
    return mod, modules


OFFSETS, OFFSETS_MODULES = _load_offsets()


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def build(db, seed_supply=True, price_minor_per_kg=100):
    store = StateStore(db)
    offsets = OFFSETS.build() if hasattr(OFFSETS, "build") else None
    if offsets is None:
        for n in dir(OFFSETS):
            if n.endswith("Core") and n != "AgentCore":
                offsets = getattr(OFFSETS, n)()
    store.register_modules("offsets", OFFSETS_MODULES)
    store.restore("offsets", offsets)
    if seed_supply:
        r = run(offsets.process({
            "action": "list_credit", "issuer": "viridis",
            "project_id": "hdfm-block-7", "mass_g": 1_000_000,
            "price_minor_per_kg": price_minor_per_kg,
            "verification_ref": "dscore:test-attestation-1"}))
        assert r["status"] == "ok", r
    weave = Weave(store, offsets)
    return store, offsets, weave


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "state.db")


class FakeConnect:
    def __init__(self, *, can_pay=True, result=None):
        self._can_pay = can_pay
        self.result = result
        self.calls = []

    def can_pay(self, payee):
        return self._can_pay

    def execute_transfer(self, payee, amount_minor, purpose_key,
                         transfer_group="", metadata=None):
        self.calls.append({"payee": payee, "amount_minor": amount_minor,
                           "purpose_key": purpose_key,
                           "transfer_group": transfer_group,
                           "metadata": metadata})
        if self.result is not None:
            return dict(self.result)
        return {"status": "ok", "transfer_id": "tr_weave_001",
                "executed_at": "2026-07-20T00:00:00Z"}


# --------------------------- WV1 --------------------------------------- #
def test_wv1_schedule_is_versioned_and_embedded(db):
    _, _, weave = build(db)
    r = run(weave.weave_event("inv-1", "lead", 7500))
    assert r["status"] == "ok"
    assert r["rate_schedule"]["version"] == "weave-B-v1"
    assert r["rate_schedule"]["rates_bps"] == {"subscription": 1000, "lead": 500}
    assert "escalator" in r["rate_schedule"]


def test_wv1_unknown_revenue_type_refused(db):
    _, _, weave = build(db)
    r = run(weave.weave_event("e-1", "consulting", 10000))
    assert r["error_type"] == "bad_revenue_type"


# --------------------------- WV2 --------------------------------------- #
def test_wv2_share_is_floor_integer_math(db):
    assert Weave.compute_share("subscription", 10000) == 1000   # 10%
    assert Weave.compute_share("lead", 7500) == 375             # 5% of $75
    assert Weave.compute_share("lead", 19) == 0                 # floors to 0
    assert Weave.compute_share("unknown", 100) is None


def test_wv2_idempotent_never_double_retires(db):
    _, offsets, weave = build(db)
    first = run(weave.weave_event("inv-75", "lead", 7500))
    replay = run(weave.weave_event("inv-75", "lead", 7500))
    assert first["duplicate"] is False and replay["duplicate"] is True
    assert replay["retirement"] == first["retirement"]
    assert weave.status()["events_woven"] == 1
    assert weave.status()["share_total_minor"] == 375


# --------------------------- WV3 --------------------------------------- #
def test_wv3_share_retires_through_clearinghouse_with_certificate(db):
    _, offsets, weave = build(db, price_minor_per_kg=100)
    r = run(weave.weave_event("inv-75", "lead", 7500))
    ret = r["retirement"]
    assert ret["purchase_id"] == "weave:inv-75"
    assert ret["retired_g"] > 0
    assert ret["spent_minor"] <= 375                  # never over budget (O9)
    assert ret["certificate_hash"]                    # O4 certificate
    purchase = run(offsets.process({"action": "get_purchase",
                                    "purchase_id": "weave:inv-75"}))
    assert purchase["status"] == "ok"
    cert = purchase["data"]
    assert cert["certificate_hash"] == ret["certificate_hash"]
    verify = run(offsets.process({"action": "verify_certificate",
                                  "certificate": cert}))
    assert verify["status"] == "ok"
    assert verify["data"]["valid"] is True            # O4 chain closes


def test_wv3_dry_run_previews_without_recording(db):
    _, offsets, weave = build(db)
    r = run(weave.weave_event("inv-preview", "lead", 7500, dry_run=True))
    assert r["preview"] is True
    assert weave.status()["events_woven"] == 0        # WV2 intact
    real = run(weave.weave_event("inv-preview", "lead", 7500))
    assert real["duplicate"] is False                 # preview didn't consume


# --------------------------- WV4 --------------------------------------- #
def test_wv4_same_account_cash_auto_executes(db):
    """Same-account allocation (EnergyAI -> Viridis Conservation, both
    under acct_1BLyFZDTpwaqE8Ss) requires no human step."""
    _, _, weave = build(db)
    r = run(weave.weave_event("inv-75", "lead", 7500))
    instr = r["cash_instruction"]
    assert instr["executed"] is True
    assert instr["executed_at"] is not None
    assert instr["scope"] == "same_account_allocation"
    assert "375" in instr["note"]
    assert "Viridis Conservation" in instr["note"]
    assert weave.status()["cash_transfers_pending"] == 0


# --------------------------- WV7 --------------------------------------- #
def test_wv7_external_connect_payee_auto_executes_exactly_once(db):
    _, _, weave = build(db)
    connect = FakeConnect()
    weave.connect = connect
    first = run(weave.weave_event(
        "external-1", "lead", 7500, payee_id="restoration:partner-1"))
    assert first["status"] == "ok"
    assert first["restoration_payee"] == "restoration:partner-1"
    instruction = first["cash_instruction"]
    assert instruction["rail"] == "connect"
    assert instruction["scope"] == "third_party_licensed_rail"
    assert instruction["executed"] is True
    assert instruction["transfer_id"] == "tr_weave_001"
    assert connect.calls == [{
        "payee": "restoration:partner-1", "amount_minor": 375,
        "purpose_key": "weave-restoration:external-1",
        "transfer_group": "external-1",
        "metadata": {"event_id": "external-1",
                     "rail": "weave-restoration"}}]
    replay = run(weave.weave_event(
        "external-1", "lead", 7500, payee_id="restoration:partner-1"))
    assert replay["duplicate"] is True
    assert len(connect.calls) == 1


def test_wv7_external_non_onboarded_payee_is_manual_with_hint(db):
    _, _, weave = build(db)
    connect = FakeConnect(can_pay=False)
    weave.connect = connect
    result = run(weave.weave_event(
        "external-2", "subscription", 10000,
        payee_id="restoration:partner-2"))
    instruction = result["cash_instruction"]
    assert instruction["rail"] == "manual"
    assert instruction["executed"] is False
    assert "action_for_justin" in instruction
    assert "begin_payout_onboarding" in instruction["onboarding_hint"]
    assert connect.calls == []
    marked = weave.mark_transfer_executed("external-2")
    assert marked["status"] == "ok" and marked["duplicate"] is False


def test_wv7_incomplete_onboarding_falls_back_but_transient_error_refuses(db):
    _, _, weave = build(db)
    incomplete = FakeConnect(result={
        "status": "error", "error_type": "payouts_not_enabled",
        "requirements_currently_due": ["external_account"]})
    weave.connect = incomplete
    result = run(weave.weave_event(
        "external-3", "lead", 7500, payee_id="restoration:partner-3"))
    assert result["cash_instruction"]["rail"] == "manual"
    assert result["cash_instruction"]["onboarding_requirements_due"] == [
        "external_account"]

    _, _, weave2 = build(str(Path(db).with_name("state-2.db")))
    transient = FakeConnect(result={
        "status": "error", "error_type": "stripe_error",
        "message": "retry"})
    weave2.connect = transient
    refused = run(weave2.weave_event(
        "external-4", "lead", 7500, payee_id="restoration:partner-4"))
    assert refused["error_type"] == "stripe_error"
    assert "external-4" not in weave2.state.events


def test_wv7_external_dry_run_never_calls_transfer(db):
    _, _, weave = build(db)
    connect = FakeConnect()
    weave.connect = connect
    preview = run(weave.weave_event(
        "external-preview", "lead", 7500, dry_run=True,
        payee_id="restoration:partner-preview"))
    assert preview["preview"] is True
    assert preview["cash_instruction"]["would_execute"] is True
    assert preview["cash_instruction"]["executed"] is False
    assert connect.calls == []
    assert "external-preview" not in weave.state.events
    # mark_transfer_executed is retained for backward-compat callers —
    # it's a no-op confirmation against an already-executed record.
    run(weave.weave_event("inv-75", "lead", 7500))
    a = weave.mark_transfer_executed("inv-75")
    b = weave.mark_transfer_executed("inv-75")
    assert a["duplicate"] is True and b["duplicate"] is True
    assert weave.status()["cash_transfers_pending"] == 0


# --------------------------- WV8 --------------------------------------- #
def test_wv8_restore_closes_only_legacy_same_account_records(db):
    store, offsets, weave = build(db)
    run(weave.weave_event("legacy-own", "lead", 7500))
    own = weave.state.events["legacy-own"]["cash_instruction"]
    own["executed"] = False
    own["executed_at"] = None
    weave.state.events["pre-wv4-own"] = {
        "event_id": "pre-wv4-own", "share_minor": 375,
        "cash_instruction": {
            "type": "restoration_share_transfer",
            "action_for_justin": (
                "move 375 minor units from EnergyAI Stripe to Viridis "
                "Conservation (restoration share, weave-B-v1)"),
            "executed": False, "executed_at": None},
        "retirement": {},
    }
    weave.state.events["legacy-external"] = {
        "event_id": "legacy-external", "share_minor": 125,
        "cash_instruction": {
            "scope": "third_party_licensed_rail", "rail": "manual",
            "executed": False, "executed_at": None},
        "retirement": {},
    }
    assert store.save("weave", weave.state)

    restored = Weave(store, offsets)
    migrated = restored.state.events["legacy-own"]["cash_instruction"]
    assert migrated["executed"] is True
    assert migrated["executed_at"]
    assert migrated["autonomy_migration"] == "FA-I1-2026-07-20"
    pre_wv4 = restored.state.events["pre-wv4-own"]
    assert pre_wv4["restoration_payee"] == "viridis:conservation"
    assert pre_wv4["cash_instruction"]["scope"] == \
        "same_account_allocation"
    assert pre_wv4["cash_instruction"]["payee"] == \
        "viridis:conservation"
    assert pre_wv4["cash_instruction"]["executed"] is True
    assert "action_for_justin" not in pre_wv4["cash_instruction"]
    assert "legacy same-account allocation" in \
        pre_wv4["cash_instruction"]["note"]
    assert restored.state.events["legacy-external"][
        "cash_instruction"]["executed"] is False

    restarted = Weave(store, offsets)
    assert restarted.state.events["legacy-own"][
        "cash_instruction"]["autonomy_migration"] == "FA-I1-2026-07-20"
    assert restarted.status()["cash_transfers_pending"] == 1


def test_wv8_migration_persist_failure_reverts_in_memory(db):
    store, offsets, weave = build(db)
    run(weave.weave_event("legacy-fail", "lead", 7500))
    weave.state.events["legacy-fail"]["cash_instruction"] = {
        "type": "restoration_share_transfer",
        "action_for_justin": (
            "move 375 minor units from EnergyAI Stripe to Viridis "
            "Conservation (restoration share, weave-B-v1)"),
        "executed": False, "executed_at": None}
    assert store.save("weave", weave.state)
    store.save = lambda *args, **kwargs: False

    restored = Weave(store, offsets)
    restored_instruction = restored.state.events[
        "legacy-fail"]["cash_instruction"]
    assert restored_instruction["executed"] is False
    assert restored_instruction["executed_at"] is None
    assert "action_for_justin" in restored_instruction
    assert "scope" not in restored_instruction
    assert "autonomy_migration" not in restored_instruction
    assert "legacy_same_account_migration" in restored.status()["errors"]


# --------------------------- WV5 --------------------------------------- #
def test_wv5_empty_book_refuses_and_records_nothing(db):
    _, _, weave = build(db, seed_supply=False)
    r = run(weave.weave_event("inv-75", "lead", 7500))
    assert r["status"] == "error"
    assert r["error_type"] == "clearinghouse_refused"
    assert weave.status()["events_woven"] == 0        # no phantom obligation


def test_wv5_persist_failure_reverts_with_safe_retry_path(db):
    _, _, weave = build(db)
    weave.store.save = lambda *a, **k: False
    r = run(weave.weave_event("inv-75", "lead", 7500))
    assert r["error_type"] == "persist_failed"
    assert "idempotent" in r["message"]               # O2 makes retry safe
    assert "inv-75" not in weave.state.events


def test_wv5_share_rounds_to_zero_refused(db):
    _, _, weave = build(db)
    r = run(weave.weave_event("tiny", "lead", 19))
    assert r["error_type"] == "share_rounds_to_zero"


# --------------------------- WV6 --------------------------------------- #
def test_wv6_ledger_is_obligation_not_revenue(db):
    _, _, weave = build(db)
    run(weave.weave_event("inv-75", "lead", 7500))
    run(weave.weave_event("sub-1", "subscription", 10000))
    s = weave.status()
    assert s["share_total_minor"] == 375 + 1000
    assert s["retired_total_g"] > 0
    assert s["cash_transfers_pending"] == 0    # auto-executed, same account
    assert "never fleet service revenue" in s["meaning"]


def test_wv6_survives_restart(db):
    _, _, weave = build(db)
    run(weave.weave_event("inv-75", "lead", 7500))

    store2 = StateStore(db)
    offsets2 = OFFSETS.build()
    store2.register_modules("offsets", OFFSETS_MODULES)
    store2.restore("offsets", offsets2)
    weave2 = Weave(store2, offsets2)
    assert weave2.status()["events_woven"] == 1
    replay = run(weave2.weave_event("inv-75", "lead", 7500))
    assert replay["duplicate"] is True
