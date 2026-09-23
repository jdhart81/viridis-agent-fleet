"""ST1-ST8 invariant tests; stdlib unittest compatible."""

import asyncio
import hashlib
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))
for module_name in [name for name in list(sys.modules)
                    if name == "src" or name.startswith("src.")]:
    del sys.modules[module_name]

from src.core import (AgentConfig, ConservationError, DATA_PATH, PLAN_CATALOG,
                      PLAN_CATALOG_SHA256, VERSION, build)


ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "deploy" / "gateway"
if str(GATEWAY) not in sys.path:
    sys.path.insert(0, str(GATEWAY))
from state_store import StateStore  # noqa: E402


def run(awaitable):
    return asyncio.run(awaitable)


class Clock:
    def __init__(self, value="2026-07-15T12:00:00Z"):
        self.set(value)

    def set(self, value):
        self.value = datetime.fromisoformat(value.replace("Z", "+00:00"))

    def __call__(self):
        return self.value


class KeyFactory:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return "vir_acct_" + (str(self.n) * 48)


class FakeStripe:
    def __init__(self):
        self.payload = None
        self.payloads = {}
        self.verify_error = None
        self.verify_calls = []
        self.checkout_calls = []
        self.portal_calls = []

    def verify_subscription(self, reference):
        self.verify_calls.append(reference)
        if self.verify_error is not None:
            raise self.verify_error
        return deepcopy(self.payloads.get(reference, self.payload))

    def create_subscription_checkout(self, **kwargs):
        self.checkout_calls.append(deepcopy(kwargs))
        return {"status": "ok",
                "url": "https://checkout.stripe.com/c/pay/cs_test",
                "livemode": True}

    def create_customer_portal(self, **kwargs):
        self.portal_calls.append(deepcopy(kwargs))
        return {"status": "ok",
                "url": "https://billing.stripe.com/p/session/test",
                "livemode": True}


CATALOG_SHA = "c" * 64


def approved_catalog(*, quota=1000):
    catalog = deepcopy(PLAN_CATALOG)
    for plan in catalog["plans"]:
        if plan["id"] == "taxcredit-seat":
            plan.update({
                "stripe_price_id": "price_TaxCreditSeat149",
                "approval_status": "approved",
                "checkout_enabled": True,
                "coverage_ready": True,
                "included_calls_per_month": quota,
            })
    catalog["configuration_notice"] = "test-approved taxcredit seat"
    return catalog


def verified_payload(*, status="active", start=1782864000, end=1785542400,
                     account_ref="buyer@example.test", livemode=True,
                     acquisition_source=None):
    # 2026-07-01 <= test clock < 2026-08-01
    payload = {
        "status": "ok",
        "verified": True,
        "mode": "subscription",
        "line_item_count": 1,
        "subscription_id": "sub_TestSeat001",
        "customer_id": "cus_TestBuyer001",
        "subscription_status": status,
        "current_period_start": start,
        "current_period_end": end,
        "price_id": "price_TaxCreditSeat149",
        "quantity": 1,
        "unit_amount": 14900,
        "currency": "usd",
        "interval": "month",
        "interval_count": 1,
        "price_active": True,
        "plan_id": "taxcredit-seat",
        "catalog_version": "0.2.0",
        "catalog_sha256": CATALOG_SHA,
        "account_ref": account_ref,
        "livemode": livemode,
    }
    if acquisition_source is not None:
        payload["acquisition_source"] = acquisition_source
    return payload


def fixture(*, quota=1000, clock=None, livemode=True):
    clock = clock or Clock()
    stripe = FakeStripe()
    stripe.payload = verified_payload(livemode=livemode)
    config = AgentConfig(
        stripe_provider=stripe,
        clock=clock,
        key_factory=KeyFactory(),
        catalog=approved_catalog(quota=quota),
        catalog_sha256=CATALOG_SHA,
        stripe_livemode_expected=livemode,
    )
    core = build(config)
    created = core.create_account("buyer@example.test")
    account_id, account_key = created["account_id"], created["account_key"]
    activated = core.record_subscription("cs_TestSeat001")
    assert activated["activation_created"] is True
    return core, stripe, clock, account_id, account_key


def reserve_and_commit(core, account_id, request_id, *, price=200):
    decision = core.reserve_entitlement(account_id, "taxcredit-engine",
                                        request_id, price)
    token = decision.get("reservation_token")
    if token:
        assert core.commit_reservation(token) is True
    return decision


class SubscriptionInvariants(unittest.TestCase):
    def test_st1_real_state_store_restart_and_no_raw_key_in_snapshot(self):
        clock, stripe = Clock(), FakeStripe()
        stripe.payload = verified_payload()
        config = AgentConfig(stripe_provider=stripe, clock=clock,
                             key_factory=KeyFactory(),
                             catalog=approved_catalog(quota=2),
                             catalog_sha256=CATALOG_SHA)
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "state.db")
            store = StateStore(db_path)
            core = build(config)
            store.attach("subscriptions", core)
            created = run(core.process({"action": "create_account",
                                        "account_ref": "buyer@example.test"}))
            self.assertEqual(created["status"], "ok")
            account_id = created["data"]["account_id"]
            raw_key = created["data"]["account_key"]
            activated = run(core.process({"action": "record_subscription",
                                          "stripe_reference": "cs_TestSeat001"}))
            self.assertEqual(activated["status"], "ok", activated)

            decision = core.reserve_entitlement(
                account_id, "taxcredit-engine", "restart-call", 200)
            token = decision["reservation_token"]
            self.assertTrue(store.save("subscriptions", core))
            self.assertTrue(core.commit_reservation(token))
            blob = store._conn.execute(
                "SELECT snapshot FROM agent_state WHERE agent='subscriptions'"
            ).fetchone()[0]
            self.assertNotIn(raw_key.encode("utf-8"), blob)
            store.close()

            restarted = build(AgentConfig(
                stripe_provider=stripe, clock=clock, key_factory=KeyFactory(),
                catalog=approved_catalog(quota=2),
                catalog_sha256=CATALOG_SHA))
            store2 = StateStore(db_path)
            self.assertTrue(store2.restore("subscriptions", restarted))
            self.assertEqual(restarted.resolve_account_key(raw_key), account_id)
            status = restarted.subscription_status(account_id, raw_key)
            self.assertEqual(status["subscriptions"][0]["included_used"], 1)
            self.assertEqual(status["account_key"], "****" + raw_key[-4:])
            store2.close()

    def test_st2_verifier_error_and_ambiguity_fail_to_per_call_without_free(self):
        core, stripe, _, account_id, _ = fixture(quota=2)
        stripe.verify_error = RuntimeError("sk_live_must_never_leak")
        failed = core.reserve_entitlement(
            account_id, "taxcredit-engine", "lookup-error", 200)
        self.assertEqual(failed["path"], "per_call_fallback")
        self.assertTrue(failed["lookup_error"])
        self.assertFalse(failed["waive_per_call_charge"])
        self.assertIsNone(failed["reservation_token"])
        self.assertEqual(core._usage[next(iter(core._usage))].included_used, 0)

        stripe.verify_error = None
        # A separately verified, overlapping active subscription covering the
        # same agent must never combine quotas or choose optimistically.
        second = deepcopy(stripe.payload)
        second["subscription_id"] = "sub_TestSeat002"
        stripe.payload = second
        core.record_subscription("cs_TestSeat002")
        stripe.payloads = {
            "sub_TestSeat001": verified_payload(),
            "sub_TestSeat002": second,
        }
        ambiguous = core.reserve_entitlement(
            account_id, "taxcredit-engine", "ambiguous", 200)
        self.assertEqual(ambiguous["path"], "per_call_fallback")
        self.assertEqual(ambiguous["reason"], "ambiguous_active_entitlement")
        self.assertFalse(ambiguous["waive_per_call_charge"])

    def test_st3_exactly_one_included_or_direct_overage_path_and_replay(self):
        core, _, _, account_id, key = fixture(quota=1)
        first = reserve_and_commit(core, account_id, "call-1")
        self.assertEqual(first["path"], "included_quota_waiver")
        self.assertTrue(first["waive_per_call_charge"])
        second = reserve_and_commit(core, account_id, "call-2", price=200)
        self.assertEqual(second["path"], "overage_meter")
        self.assertEqual(second["overage_minor"], 200)
        self.assertTrue(second["bypass_anonymous_freemium"])
        self.assertTrue(second["requires_direct_overage_charge"])

        replay = core.reserve_entitlement(
            account_id, "taxcredit-engine", "call-2", 200)
        self.assertTrue(replay["idempotent_replay"])
        self.assertIsNone(replay["reservation_token"])
        self.assertFalse(replay["durability_required"])
        summary = core.usage_summary(account_id, key)
        self.assertEqual(summary["totals"], {
            "included_used": 1, "overage_calls": 1,
            "overage_minor": 200, "used_calls": 2,
        })

    def test_st4_lifecycle_half_open_no_grace_and_native_status_mapping(self):
        mappings = {
            "past_due": "past_due", "unpaid": "past_due",
            "canceled": "canceled", "incomplete_expired": "expired",
            "trialing": "expired", "incomplete": "expired",
            "paused": "expired",
        }
        for stripe_status, expected in mappings.items():
            with self.subTest(stripe_status=stripe_status):
                clock, stripe = Clock(), FakeStripe()
                stripe.payload = verified_payload(status=stripe_status)
                core = build(AgentConfig(
                    stripe_provider=stripe, clock=clock,
                    key_factory=KeyFactory(), catalog=approved_catalog(),
                    catalog_sha256=CATALOG_SHA))
                account = core.create_account("buyer@example.test")
                record = core.record_subscription("cs_TestSeat001")
                self.assertEqual(record["status"], expected)
                decision = core.reserve_entitlement(
                    account["account_id"], "taxcredit-engine",
                    f"native-{stripe_status}", 200)
                token = decision.get("reservation_token")
                if token:
                    core.commit_reservation(token)
                self.assertEqual(decision["path"], "per_call_fallback")
                self.assertEqual(core.mrr_summary()["mrr_minor"], 0)

        # Exactly at period_end is expired (half-open interval), even if the
        # provider still reports active.
        clock = Clock("2026-08-01T00:00:00Z")
        core, _, _, account_id, _ = fixture(clock=clock)
        expired = core.reserve_entitlement(
            account_id, "taxcredit-engine", "at-end", 200)
        self.assertEqual(expired["path"], "per_call_fallback")
        self.assertEqual(core.mrr_summary()["active_subscriptions"], 0)

        # Unknown future Stripe status is verification failure, never active.
        core2, stripe2, _, account_id2, _ = fixture()
        stripe2.payload["subscription_status"] = "future_unknown_status"
        unknown = core2.reserve_entitlement(
            account_id2, "taxcredit-engine", "unknown-status", 200)
        self.assertEqual(unknown["path"], "per_call_fallback")
        self.assertTrue(unknown["lookup_error"])

    def test_st5_activation_replay_is_idempotent_but_lifecycle_can_refresh(self):
        core, stripe, _, _, _ = fixture()
        before_events = len([e for e in core._audit_events
                             if e["event_type"] == "subscription_period_activated"])
        replay = core.record_subscription("sub_TestSeat001")
        self.assertFalse(replay["activation_created"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(len(core._activation_keys), 1)
        self.assertEqual(len([e for e in core._audit_events
                              if e["event_type"] == "subscription_period_activated"]),
                         before_events)

        stripe.payload["subscription_status"] = "past_due"
        refresh = core.record_subscription("sub_TestSeat001")
        self.assertFalse(refresh["activation_created"])
        self.assertEqual(refresh["status"], "past_due")
        self.assertEqual(len(core._activation_keys), 1)
        self.assertEqual(len(core._usage), 1)

    def test_activation_commit_is_durable_before_one_time_key_ack(self):
        stripe = FakeStripe()
        stripe.payload = verified_payload()
        observed = {}
        holder = {}

        def durable_commit():
            core = holder["core"]
            observed.update({
                "accounts": len(core._accounts),
                "account_refs": len(core._account_by_ref),
                "account_keys": len(core._account_by_key),
                "subscriptions": len(core._subscriptions),
                "periods": len(core._periods),
                "activation_keys": len(core._activation_keys),
                "usage": len(core._usage),
                "activation_events": len([
                    event for event in core._audit_events
                    if event["event_type"] == "subscription_period_activated"
                ]),
            })
            return True

        core = build(AgentConfig(
            stripe_provider=stripe, clock=Clock(), key_factory=KeyFactory(),
            catalog=approved_catalog(), catalog_sha256=CATALOG_SHA,
            durable_activation_commit=durable_commit))
        holder["core"] = core

        result = run(core.process({
            "action": "record_subscription",
            "stripe_reference": "cs_TestSeat001",
        }))
        self.assertEqual(result["status"], "ok", result)
        self.assertTrue(result["data"]["activation_created"])
        self.assertTrue(result["data"]["account_key_issued_once"])
        self.assertTrue(result["data"]["account_key"].startswith("vir_acct_"))
        self.assertEqual(observed, {
            "accounts": 1,
            "account_refs": 1,
            "account_keys": 1,
            "subscriptions": 1,
            "periods": 1,
            "activation_keys": 1,
            "usage": 1,
            "activation_events": 1,
        })

    def test_activation_commit_failure_or_exception_rolls_back_and_retries(self):
        for failure_mode in ("false", "raise"):
            with self.subTest(failure_mode=failure_mode):
                stripe = FakeStripe()
                stripe.payload = verified_payload()

                def failed_commit():
                    if failure_mode == "raise":
                        raise RuntimeError("sk_live_must_never_be_logged")
                    return False

                core = build(AgentConfig(
                    stripe_provider=stripe, clock=Clock(),
                    key_factory=KeyFactory(), catalog=approved_catalog(),
                    catalog_sha256=CATALOG_SHA,
                    durable_activation_commit=failed_commit))
                # Preserve non-activation state too, proving the complete
                # rollback does not rewind or invent front-door metrics.
                core.record_frontdoor_view()
                before = core._transaction_snapshot()

                with self.assertLogs("subscriptions-agent", level="WARNING") as logs:
                    failed = run(core.process({
                        "action": "record_subscription",
                        "stripe_reference": "cs_TestSeat001",
                    }))
                self.assertEqual(failed["status"], "error")
                self.assertEqual(failed["error_type"], "DurabilityError")
                self.assertFalse(failed["entitled"])
                self.assertFalse(failed["account_key_issued_once"])
                self.assertNotIn("account_key", failed)
                self.assertNotIn("sk_live_must_never_be_logged",
                                 json.dumps(failed))
                self.assertNotIn("sk_live_must_never_be_logged",
                                 "\n".join(logs.output))
                self.assertEqual(core._transaction_snapshot(), before)
                self.assertEqual(len(core._accounts), 0)
                self.assertEqual(len(core._account_by_ref), 0)
                self.assertEqual(len(core._account_by_key), 0)
                self.assertEqual(len(core._subscriptions), 0)
                self.assertEqual(len(core._periods), 0)
                self.assertEqual(len(core._activation_keys), 0)
                self.assertEqual(len(core._usage), 0)

                # A failed acknowledgement consumed no activation or key;
                # fixing durability lets a later retry issue the key once.
                core.config.durable_activation_commit = lambda: True
                retried = run(core.process({
                    "action": "record_subscription",
                    "stripe_reference": "cs_TestSeat001",
                }))
                self.assertEqual(retried["status"], "ok", retried)
                self.assertTrue(retried["data"]["activation_created"])
                self.assertTrue(retried["data"]["account_key_issued_once"])
                self.assertIn("account_key", retried["data"])

    def test_activation_replay_does_not_invoke_second_durable_commit(self):
        stripe = FakeStripe()
        stripe.payload = verified_payload()
        commits = []

        def durable_commit():
            commits.append("commit")
            return True

        core = build(AgentConfig(
            stripe_provider=stripe, clock=Clock(), key_factory=KeyFactory(),
            catalog=approved_catalog(), catalog_sha256=CATALOG_SHA,
            durable_activation_commit=durable_commit))
        first = run(core.process({
            "action": "record_subscription",
            "stripe_reference": "cs_TestSeat001",
        }))
        replay = run(core.process({
            "action": "record_subscription",
            "stripe_reference": "sub_TestSeat001",
        }))
        self.assertEqual(first["status"], "ok")
        self.assertEqual(replay["status"], "ok")
        self.assertEqual(commits, ["commit"])
        self.assertTrue(replay["data"]["idempotent_replay"])
        self.assertFalse(replay["data"]["account_key_issued_once"])
        self.assertNotIn("account_key", replay["data"])

    def test_health_reports_durable_activation_commit_attachment(self):
        unwired = run(build().health())
        wired = run(build(AgentConfig(
            durable_activation_commit=lambda: True)).health())
        self.assertFalse(
            unwired["checks"]["durable_activation_commit_attached"])
        self.assertTrue(
            wired["checks"]["durable_activation_commit_attached"])

    def test_st6_no_secrets_hosted_links_only_and_draft_checkout_fails_closed(self):
        draft = build()
        result = run(draft.process({"action": "create_checkout_link",
                                    "plan_id": "ghg-seat",
                                    "account_ref": "buyer@example.test"}))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "configuration_required")
        self.assertEqual(len(draft._accounts), 0)

        core, stripe, _, account_id, account_key = fixture()
        link = core.create_checkout_link("taxcredit-seat", "buyer@example.test")
        self.assertTrue(link["checkout_url"].startswith(
            "https://checkout.stripe.com/"))
        portal = core.customer_portal_link(account_id, account_key)
        self.assertTrue(portal["portal_url"].startswith(
            "https://billing.stripe.com/"))
        self.assertEqual(stripe.checkout_calls[0]["catalog_sha256"], CATALOG_SHA)

        denied = run(core.process({"action": "subscription_status",
                                   "account_id": account_id,
                                   "account_key": "wrong-bearer"}))
        self.assertEqual(denied["status"], "error")
        self.assertNotIn(account_key, repr(vars(core)))

        stripe.payload["quantity"] = True  # bool must not pass integer exactness
        non_integer = run(core.process({"action": "record_subscription",
                                        "stripe_reference": "sub_TestSeat001"}))
        self.assertEqual(non_integer["status"], "error")
        self.assertEqual(non_integer["error_type"], "VerificationError")
        stripe.payload["quantity"] = 1

        stripe.verify_error = RuntimeError("sk_live_do_not_return_this")
        generic = run(core.process({"action": "record_subscription",
                                    "stripe_reference": "sub_TestSeat001"}))
        self.assertNotIn("sk_live_do_not_return_this", json.dumps(generic))

        bad_catalog = approved_catalog()
        next(p for p in bad_catalog["plans"]
             if p["id"] == "taxcredit-seat")["stripe_price_id"] = "price_bad-hyphen"
        malformed = build(AgentConfig(catalog=bad_catalog,
                                      catalog_sha256=CATALOG_SHA))
        invalid = run(malformed.process({"action": "list_plans"}))
        self.assertEqual(invalid["status"], "error")

    def test_st7_verified_new_period_resets_only_new_counter_and_conserves(self):
        core, stripe, _, account_id, key = fixture(quota=1)
        reserve_and_commit(core, account_id, "old-period")
        old_key = next(iter(core._usage))
        self.assertEqual(core._usage[old_key].included_used, 1)

        stripe.payload = verified_payload(
            start=1785542400, end=1788220800)  # 2026-08-01 -> 2026-09-01
        rollover = core.record_subscription("sub_TestSeat001")
        self.assertTrue(rollover["activation_created"])
        self.assertEqual(len(core._activation_keys), 2)
        new_key = core._subscriptions["sub_TestSeat001"].current_period_key
        self.assertNotEqual(old_key, new_key)
        self.assertEqual(core._usage[new_key].included_used, 0)

        # Move clock into the newly verified period before consuming it.
        core.config.clock.set("2026-08-02T00:00:00Z")
        new = reserve_and_commit(core, account_id, "new-period")
        self.assertEqual(new["path"], "included_quota_waiver")
        summary = core.usage_summary(account_id, key)
        self.assertEqual(len(summary["periods"]), 2)
        self.assertEqual(summary["totals"]["included_used"], 2)
        self.assertEqual(summary["totals"]["used_calls"], 2)
        self.assertEqual(len(summary["audit_sha256"]), 64)

        # Any counter/decision drift fails loud rather than reporting a
        # plausible-looking revenue or quota number.
        core._usage[new_key].included_used += 1
        drift = run(core.process({"action": "usage_summary",
                                  "account_id": account_id,
                                  "account_key": key}))
        self.assertEqual(drift["status"], "error")
        self.assertEqual(drift["error_type"], "ConservationError")
        core._usage[new_key].included_used -= 1

        # Overlap is verified but rejected; local time never guesses rollover.
        stripe.payload = verified_payload(
            start=1787000000, end=1790812800)
        overlap = run(core.process({"action": "record_subscription",
                                    "stripe_reference": "sub_TestSeat001"}))
        self.assertEqual(overlap["status"], "error")
        self.assertEqual(len(core._activation_keys), 2)

    def test_st8_catalog_bundle_digest_and_decision_lineage_are_exact(self):
        core, _, _, account_id, _ = fixture()
        listed = build().list_plans()
        self.assertEqual(DATA_PATH.name, "plan_catalog.v0.2.0.json")
        self.assertEqual(listed["pack_version"], "0.2.0")
        self.assertEqual(listed["plan_catalog_sha256"], PLAN_CATALOG_SHA256)
        energy = next(plan for plan in listed["plans"]
                      if plan["id"] == "energy-seat")
        self.assertEqual(energy["covered_agents"], [
            "disclosure-compiler", "ghg-ledger", "taxcredit-engine"])
        self.assertEqual(energy["price_minor"], 24900)
        self.assertEqual(energy["included_calls_per_month"], 1000)
        self.assertTrue(energy["coverage_ready"])
        self.assertFalse(energy["checkout_enabled"])

        for plan_id in ("energy-seat", "climate-seat", "compliance-seat"):
            plan = next(item for item in listed["plans"]
                        if item["id"] == plan_id)
            self.assertTrue(plan["coverage_ready"])
            self.assertTrue(plan["configuration_required"])
            self.assertEqual(plan["checkout_status"],
                             "configuration_required")
            self.assertIsNone(plan["stripe_price_id"])
            self.assertEqual(plan["approval_status"], "draft")
            self.assertFalse(plan["checkout_enabled"])

        decision = reserve_and_commit(core, account_id, "catalog-lineage")
        self.assertEqual(decision["catalog"], {
            "version": "0.2.0", "sha256": CATALOG_SHA})
        self.assertEqual(core.mrr_summary(), {
            "active_subscriptions": 1,
            "mrr_minor": 14900,
            "currency": "usd",
            "plan_mix": {"taxcredit-seat": {
                "active_subscriptions": 1, "mrr_minor": 14900}},
            "catalog": {"version": "0.2.0", "sha256": CATALOG_SHA},
        })
        test_core, _, _, _, _ = fixture(livemode=False)
        self.assertEqual(test_core.mrr_summary()["mrr_minor"], 0)

    def test_account_key_auth_attributes_without_exposing_raw_key(self):
        core, _, _, account_id, account_key = fixture()
        self.assertEqual(core.resolve_account_key(account_key), account_id)
        self.assertIsNone(core.resolve_account_key("not-the-key"))
        status = core.subscription_status(account_id, account_key)
        self.assertEqual(status["account_id"], account_id)
        self.assertEqual(status["account_key"], "****" + account_key[-4:])
        self.assertNotEqual(status["account_key"], account_key)

    def test_frontdoor_metrics_count_only_views_and_validated_checkout_links(self):
        stripe = FakeStripe()
        config = AgentConfig(
            stripe_provider=stripe, clock=Clock(), key_factory=KeyFactory(),
            catalog=approved_catalog(), catalog_sha256=CATALOG_SHA)
        core = build(config)

        first = run(core.process({
            "action": "record_frontdoor_view", "source": "meshmcp"}))
        second = run(core.process({"action": "record_frontdoor_view"}))
        self.assertEqual(first["data"]["page_views"], 1)
        self.assertEqual(second["data"]["page_views"], 2)

        # A provider error or a non-Stripe redirect must not enter the funnel.
        stripe.create_subscription_checkout = lambda **_kwargs: {
            "status": "error", "livemode": True}
        failed = run(core.process({
            "action": "create_checkout_link", "plan_id": "taxcredit-seat",
            "account_ref": "buyer@example.test"}))
        self.assertEqual(failed["status"], "error")
        self.assertEqual(core.frontdoor_summary()["checkouts_started"], 0)

        stripe.create_subscription_checkout = lambda **_kwargs: {
            "status": "ok", "url": "https://example.test/not-stripe",
            "livemode": True}
        untrusted = run(core.process({
            "action": "create_checkout_link", "plan_id": "taxcredit-seat",
            "account_ref": "buyer@example.test"}))
        self.assertEqual(untrusted["status"], "error")
        self.assertEqual(core.frontdoor_summary()["checkouts_started"], 0)

        stripe.create_subscription_checkout = lambda **_kwargs: {
            "status": "ok",
            "url": "https://checkout.stripe.com/c/pay/cs_live_frontdoor",
            "livemode": True}
        checkout = run(core.process({
            "action": "create_checkout_link", "plan_id": "taxcredit-seat",
            "account_ref": "buyer@example.test"}))
        self.assertEqual(checkout["status"], "ok")
        summary = run(core.process({"action": "frontdoor_summary"}))["data"]
        self.assertEqual(summary["page_views"], 2)
        self.assertEqual(summary["checkouts_started"], 1)
        self.assertEqual(summary["snapshot_page_views"], 0)
        self.assertEqual(summary["snapshot_checkouts_started"], 0)
        self.assertEqual(summary["snapshot_paid"], 0)
        self.assertEqual(summary["seat_source_views"]["meshmcp"], 1)
        self.assertEqual(summary["seat_attributed_views"], 1)
        self.assertEqual(summary["seat_unattributed_views"], 1)
        self.assertEqual(
            summary["seat_acquisition_classification"],
            "seller_reported_aggregate_telemetry_not_unique_buyers_"
            "and_not_revenue")
        self.assertEqual(summary["active_subscriptions"], 0)
        health = run(core.health())
        self.assertEqual(health["checks"]["page_views"], 2)
        self.assertEqual(health["checks"]["checkouts_started"], 1)
        self.assertEqual(health["checks"]["seat_source_views"]["meshmcp"], 1)
        invalid = run(core.process({
            "action": "record_frontdoor_view",
            "source": "https://discord.com/channels/private",
        }))
        self.assertEqual(invalid["status"], "error")
        self.assertEqual(invalid["error_type"], "ValidationError")
        self.assertEqual(core.frontdoor_summary()["page_views"], 2)

    def test_complete_seat_source_journey_survives_activation_and_renewal(self):
        stripe = FakeStripe()
        stripe.payload = verified_payload(acquisition_source="github")
        core = build(AgentConfig(
            stripe_provider=stripe,
            clock=Clock(),
            key_factory=KeyFactory(),
            catalog=approved_catalog(),
            catalog_sha256=CATALOG_SHA,
        ))
        run(core.process({
            "action": "record_frontdoor_view",
            "source": "github",
        }))
        checkout = run(core.process({
            "action": "create_checkout_link",
            "plan_id": "taxcredit-seat",
            "account_ref": "buyer@example.test",
            "acquisition_source": "github",
        }))
        self.assertEqual(checkout["status"], "ok")
        self.assertEqual(
            stripe.checkout_calls[0]["acquisition_source"], "github")

        activated = core.record_subscription("cs_TestSeat001")
        self.assertTrue(activated["activation_created"])
        summary = core.frontdoor_summary()
        self.assertEqual(summary["seat_source_views"]["github"], 1)
        self.assertEqual(summary["seat_funnel_by_source"]["github"], {
            "checkout_starts": 1,
            "paid": 1,
            "activated": 1,
            "renewed": 0,
        })

        replay = core.record_subscription("sub_TestSeat001")
        self.assertFalse(replay["activation_created"])
        self.assertEqual(
            core.frontdoor_summary()["seat_funnel_by_source"]["github"][
                "renewed"], 0)

        stripe.payload = verified_payload(
            start=1785542400,
            end=1788220800,
            acquisition_source="github",
        )
        renewed = core.record_subscription("sub_TestSeat001")
        self.assertTrue(renewed["activation_created"])
        self.assertEqual(
            core.frontdoor_summary()["seat_funnel_by_source"]["github"], {
                "checkout_starts": 1,
                "paid": 1,
                "activated": 1,
                "renewed": 1,
            })
        encoded = json.dumps(core.frontdoor_summary(), sort_keys=True)
        self.assertNotIn("buyer@example.test", encoded)
        self.assertNotIn("sub_TestSeat001", encoded)

    def test_subscription_source_change_fails_closed(self):
        core, stripe, _, _, _ = fixture()
        stripe.payload["acquisition_source"] = "github"
        # The historical activation was explicitly unattributed; adding a
        # source later does not backfill or rewrite its cohort.
        replay = core.record_subscription("sub_TestSeat001")
        self.assertFalse(replay["activation_created"])
        self.assertEqual(
            core.frontdoor_summary()["seat_funnel_by_source"][
                "unattributed"]["activated"], 1)

        fresh = FakeStripe()
        fresh.payload = verified_payload(acquisition_source="github")
        sourced = build(AgentConfig(
            stripe_provider=fresh,
            clock=Clock(),
            key_factory=KeyFactory(),
            catalog=approved_catalog(),
            catalog_sha256=CATALOG_SHA,
        ))
        sourced.record_subscription("cs_TestSeat001")
        fresh.payload["acquisition_source"] = "search"
        changed = run(sourced.process({
            "action": "record_subscription",
            "stripe_reference": "sub_TestSeat001",
        }))
        self.assertEqual(changed["status"], "error")
        self.assertEqual(changed["error_type"], "VerificationError")

    def test_retention_summary_tracks_unused_value_and_renewal_risk(self):
        core, stripe, clock, account_id, _ = fixture()
        fresh = core.retention_summary()
        self.assertEqual(fresh["activation"], {
            "active_used": 0,
            "active_unused": 1,
            "active_unused_over_7d": 0,
            "active_used_last_value_unknown": 0,
        })
        self.assertEqual(fresh["renewal"], {
            "healthy": 1,
            "due_within_7d": 0,
            "failed": 0,
            "canceled": 0,
            "expired": 0,
        })
        self.assertEqual(
            fresh["paid_not_activated_status"],
            "unavailable_without_provider_checkout_reconciliation",
        )

        reserve_and_commit(core, account_id, "retention-value-1")
        valued = core.retention_summary()
        self.assertEqual(valued["activation"]["active_used"], 1)
        self.assertEqual(valued["activation"]["active_unused"], 0)
        self.assertEqual(valued["last_value_at"], "2026-07-15T12:00:00Z")
        self.assertEqual(
            valued["last_value_status"], "complete_for_observed_usage")

        clock.set("2026-07-28T12:00:00Z")
        due = core.retention_summary()
        self.assertEqual(due["renewal"]["due_within_7d"], 1)

        stripe.payload["subscription_status"] = "past_due"
        core.record_subscription("sub_TestSeat001")
        failed = core.retention_summary()
        self.assertEqual(failed["active_subscriptions"], 0)
        self.assertEqual(failed["renewal"]["failed"], 1)
        self.assertEqual(failed["activation"]["active_used"], 0)
        encoded = json.dumps(failed, sort_keys=True)
        self.assertNotIn(account_id, encoded)
        self.assertNotIn("sub_TestSeat001", encoded)

    def test_retention_summary_flags_unused_after_seven_days(self):
        core, _, clock, _, _ = fixture()
        clock.set("2026-07-23T12:00:00Z")
        summary = core.retention_summary()
        self.assertEqual(summary["activation"]["active_unused"], 1)
        self.assertEqual(
            summary["activation"]["active_unused_over_7d"], 1)

    def test_historical_used_counter_without_timestamp_is_explicit(self):
        core, _, _, account_id, _ = fixture()
        reserve_and_commit(core, account_id, "historical-value-1")
        usage = next(iter(core._usage.values()))
        del usage.last_used_at
        summary = core.retention_summary()
        self.assertEqual(
            summary["activation"]["active_used_last_value_unknown"], 1)
        self.assertIsNone(summary["last_value_at"])
        self.assertEqual(
            summary["last_value_status"], "historical_gaps_present")

    def test_authenticated_subscription_status_exposes_recovery_fields(self):
        core, _, _, account_id, account_key = fixture()
        status = core.subscription_status(account_id, account_key)
        seat = status["subscriptions"][0]
        self.assertEqual(seat["activation_state"], "unused")
        self.assertIsNone(seat["last_value_at"])
        self.assertEqual(seat["renewal_state"], "healthy")
        health = run(core.health())
        self.assertEqual(
            health["retention_summary"], core.retention_summary())

    def test_provider_activation_reconciliation_is_aggregate_and_read_only(self):
        core, _, _, _, _ = fixture()
        before = core._transaction_snapshot()
        observed = "2026-07-30T12:00:00Z"
        created_after = 1782864000
        evidence = [
            {
                "session_id": "cs_live_active",
                "subscription_id": "sub_TestSeat001",
                "checkout_status": "complete",
                "payment_status": "paid",
                "created": 1785369600,
                "livemode": True,
            },
            {
                "session_id": "cs_live_orphan",
                "subscription_id": "sub_NotActivated002",
                "checkout_status": "complete",
                "payment_status": "paid",
                "created": 1785369601,
                "livemode": True,
            },
            {
                "session_id": "cs_live_open",
                "subscription_id": None,
                "checkout_status": "open",
                "payment_status": "unpaid",
                "created": 1785369602,
                "livemode": True,
            },
            {
                "session_id": "cs_live_expired",
                "subscription_id": None,
                "checkout_status": "expired",
                "payment_status": "unpaid",
                "created": 1785369603,
                "livemode": True,
            },
            {
                "session_id": "cs_test_paid",
                "subscription_id": "sub_TestMode003",
                "checkout_status": "complete",
                "payment_status": "paid",
                "created": 1785369604,
                "livemode": False,
            },
        ]
        result = core.provider_activation_reconciliation(
            evidence,
            observed_at=observed,
            created_after_epoch=created_after,
            pages=2,
        )
        self.assertEqual(result["complete_paid"], 2)
        self.assertEqual(result["activated"], 1)
        self.assertEqual(result["paid_not_activated"], 1)
        self.assertEqual(result["open_unpaid"], 1)
        self.assertEqual(result["expired_unpaid"], 1)
        self.assertEqual(result["test_sessions_excluded"], 1)
        self.assertEqual(result["identifiers_returned"], 0)
        self.assertFalse(result["provider_mutation"])
        self.assertFalse(result["customer_action_authorized"])
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn("cs_live_", encoded)
        self.assertNotIn("sub_", encoded)
        self.assertEqual(core._transaction_snapshot(), before)

    def test_provider_activation_reconciliation_refuses_drift(self):
        core, _, _, _, _ = fixture()
        base = {
            "session_id": "cs_live_duplicate",
            "subscription_id": "sub_TestSeat001",
            "checkout_status": "complete",
            "payment_status": "paid",
            "created": 1785369600,
            "livemode": True,
        }
        for evidence in (
            [base, deepcopy(base)],
            [{**base, "created": 1}],
            [{**base, "checkout_status": "unknown"}],
        ):
            with self.assertRaises(Exception):
                core.provider_activation_reconciliation(
                    evidence,
                    observed_at="2026-07-30T12:00:00Z",
                    created_after_epoch=1782864000,
                    pages=1,
                )

    def test_snapshot_funnel_counts_views_checkout_and_paid_once(self):
        core = build(AgentConfig(clock=Clock(), key_factory=KeyFactory()))

        view = run(core.process({"action": "record_snapshot_view"}))
        checkout = run(core.process({
            "action": "record_snapshot_checkout_started"}))
        paid = run(core.process({
            "action": "record_snapshot_paid",
            "stripe_reference": "cs_live_snapshot_001"}))
        replay = run(core.process({
            "action": "record_snapshot_paid",
            "stripe_reference": "cs_live_snapshot_001"}))

        self.assertEqual(view["data"]["snapshot_page_views"], 1)
        self.assertEqual(
            checkout["data"]["snapshot_checkouts_started"], 1)
        self.assertTrue(paid["data"]["recorded"])
        self.assertFalse(replay["data"]["recorded"])
        self.assertTrue(replay["data"]["idempotent_replay"])
        summary = core.frontdoor_summary()
        self.assertEqual(summary["snapshot_page_views"], 1)
        self.assertEqual(summary["snapshot_checkouts_started"], 1)
        self.assertEqual(summary["snapshot_paid"], 1)
        encoded = json.dumps(core._transaction_snapshot(), sort_keys=True,
                             default=list)
        self.assertNotIn("cs_live_snapshot_001", encoded)

    def test_old_frontdoor_snapshot_normalizes_new_metrics_to_zero(self):
        core = build(AgentConfig(clock=Clock(), key_factory=KeyFactory()))
        core._frontdoor_metrics = {
            "page_views": 0,
            "checkouts_started": 0,
        }
        del core._snapshot_paid_sessions
        del core._acquisition_surface_views
        del core._acquisition_source_views
        del core._seat_source_views
        del core._seat_funnel_by_source
        del core._subscription_acquisition_source

        summary = core.frontdoor_summary()

        self.assertEqual(summary["snapshot_page_views"], 0)
        self.assertEqual(summary["snapshot_checkouts_started"], 0)
        self.assertEqual(summary["snapshot_paid"], 0)
        self.assertEqual(summary["landing_page_views"], 0)
        self.assertEqual(summary["acquisition_surface_views"], {
            "agents": 0, "quickstart": 0})
        self.assertEqual(sum(
            summary["acquisition_source_views"].values()), 0)
        self.assertEqual(sum(summary["seat_source_views"].values()), 0)
        self.assertEqual(summary["seat_attributed_views"], 0)
        self.assertEqual(summary["seat_unattributed_views"], 0)
        self.assertEqual(
            sum(
                stage
                for values in summary["seat_funnel_by_source"].values()
                for stage in values.values()
            ),
            0,
        )

    def test_old_subscription_snapshot_migrates_to_unattributed(self):
        core, _, _, _, _ = fixture()
        del core._seat_funnel_by_source
        del core._subscription_acquisition_source
        summary = core.frontdoor_summary()
        self.assertEqual(summary["seat_funnel_by_source"]["unattributed"], {
            "checkout_starts": 0,
            "paid": 1,
            "activated": 1,
            "renewed": 0,
        })
        self.assertEqual(
            core._subscription_acquisition_source["sub_TestSeat001"],
            "unattributed",
        )

    def test_previous_attribution_schema_adds_new_finite_sources_at_zero(self):
        core = build(AgentConfig(clock=Clock(), key_factory=KeyFactory()))
        core._acquisition_source_views.pop("x402_success")
        core._seat_source_views.pop("x402_success")
        core._acquisition_source_views.pop("openclaw")
        core._seat_source_views.pop("openclaw")

        summary = core.frontdoor_summary()

        self.assertEqual(
            summary["acquisition_source_views"]["x402_success"], 0)
        self.assertEqual(summary["seat_source_views"]["x402_success"], 0)
        self.assertEqual(summary["acquisition_source_views"]["openclaw"], 0)
        self.assertEqual(summary["seat_source_views"]["openclaw"], 0)

    def test_acquisition_views_are_finite_aggregate_and_conserved(self):
        core = build(AgentConfig(clock=Clock(), key_factory=KeyFactory()))

        github = run(core.process({
            "action": "record_acquisition_view",
            "surface": "agents", "source": "github"}))
        partner = run(core.process({
            "action": "record_acquisition_view",
            "surface": "quickstart", "source": "awesome_x402"}))
        invalid = run(core.process({
            "action": "record_acquisition_view",
            "surface": "agents",
            "source": "https://github.com/xpaysh/awesome-x402?buyer=private",
        }))

        self.assertEqual(github["status"], "ok")
        self.assertEqual(partner["status"], "ok")
        self.assertEqual(invalid["status"], "error")
        summary = core.frontdoor_summary()
        self.assertEqual(summary["landing_page_views"], 2)
        self.assertEqual(summary["acquisition_surface_views"], {
            "agents": 1, "quickstart": 1})
        self.assertEqual(summary["acquisition_source_views"]["github"], 1)
        self.assertEqual(
            summary["acquisition_source_views"]["awesome_x402"], 1)
        self.assertEqual(
            summary["acquisition_classification"],
            "seller_reported_aggregate_telemetry_not_revenue")
        encoded = json.dumps(
            core._transaction_snapshot(), sort_keys=True, default=list)
        self.assertNotIn("buyer=private", encoded)
        self.assertNotIn("xpaysh", encoded)

        core._acquisition_source_views["github"] += 1
        with self.assertRaises(ConservationError):
            core.frontdoor_summary()

    def test_frontdoor_metrics_persist_without_account_ref_or_hosted_url(self):
        stripe = FakeStripe()
        stripe.create_subscription_checkout = lambda **_kwargs: {
            "status": "ok",
            "url": "https://checkout.stripe.com/c/pay/cs_live_private",
            "livemode": True}
        config = AgentConfig(
            stripe_provider=stripe, clock=Clock(), key_factory=KeyFactory(),
            catalog=approved_catalog(), catalog_sha256=CATALOG_SHA)
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "frontdoor.db")
            store = StateStore(db_path)
            core = build(config)
            store.attach("subscriptions", core)
            run(core.process({
                "action": "record_frontdoor_view", "source": "meshmcp"}))
            run(core.process({
                "action": "record_acquisition_view",
                "surface": "agents", "source": "github"}))
            run(core.process({
                "action": "create_checkout_link",
                "plan_id": "taxcredit-seat",
                "account_ref": "private-buyer@example.test"}))
            blob = store._conn.execute(
                "SELECT snapshot FROM agent_state WHERE agent='subscriptions'"
            ).fetchone()[0]
            self.assertNotIn(b"private-buyer@example.test", blob)
            self.assertNotIn(b"cs_live_private", blob)
            self.assertNotIn(b"checkout.stripe.com", blob)
            self.assertNotIn(b"github.com", blob)
            store.close()

            restarted = build(AgentConfig(
                stripe_provider=stripe, clock=Clock(), key_factory=KeyFactory(),
                catalog=approved_catalog(), catalog_sha256=CATALOG_SHA))
            store2 = StateStore(db_path)
            self.assertTrue(store2.restore("subscriptions", restarted))
            self.assertEqual(restarted.frontdoor_summary()["page_views"], 1)
            self.assertEqual(
                restarted.frontdoor_summary()["checkouts_started"], 1)
            self.assertEqual(
                restarted.frontdoor_summary()["landing_page_views"], 1)
            self.assertEqual(
                restarted.frontdoor_summary()[
                    "acquisition_source_views"]["github"], 1)
            self.assertEqual(
                restarted.frontdoor_summary()[
                    "seat_source_views"]["meshmcp"], 1)
            self.assertEqual(
                restarted.frontdoor_summary()["seat_attributed_views"], 1)
            self.assertEqual(
                restarted.frontdoor_summary()["seat_unattributed_views"], 0)
            store2.close()

    def test_frontdoor_summary_is_aggregate_only_and_metric_drift_fails_loud(self):
        core, _, _, _, _ = fixture()
        summary = core.frontdoor_summary()
        self.assertEqual(summary["active_subscriptions"], 1)
        self.assertEqual(summary["mrr_minor"], 14900)
        encoded = json.dumps(summary, sort_keys=True)
        for forbidden in (
                "account_id", "account_ref", "account_key", "subscription_id",
                "stripe", "checkout_url", "portal_url", "client_reference_id"):
            self.assertNotIn(forbidden, encoded)

        core._frontdoor_metrics["page_views"] = True
        drift = run(core.process({"action": "frontdoor_summary"}))
        self.assertEqual(drift["status"], "error")
        self.assertEqual(drift["error_type"], "ConservationError")

        core = build(AgentConfig(clock=Clock(), key_factory=KeyFactory()))
        run(core.process({
            "action": "record_frontdoor_view", "source": "github"}))
        core._seat_source_views["github"] += 1
        drift = run(core.process({"action": "frontdoor_summary"}))
        self.assertEqual(drift["status"], "error")
        self.assertEqual(drift["error_type"], "ConservationError")

    def test_plan_reads_annotate_readiness_without_mutating_catalog_or_sha(self):
        bundled_before = deepcopy(PLAN_CATALOG)

        # The bundled draft catalog is not ready, and an approved catalog still
        # fails closed when its hosted-link provider is absent.
        draft = build().list_plans()
        self.assertTrue(all(
            plan["checkout_status"] == "configuration_required" and
            plan["configuration_required"] is True
            for plan in draft["plans"]))
        no_provider = build(AgentConfig(
            catalog=approved_catalog(), catalog_sha256=CATALOG_SHA))
        unavailable = no_provider.get_plan("taxcredit-seat")["plan"]
        self.assertEqual(unavailable["checkout_status"],
                         "configuration_required")
        self.assertTrue(unavailable["configuration_required"])

        # Attaching the provider flips exactly the fully configured plan.  No
        # provider internals or credentials become part of the read shape.
        stripe = FakeStripe()
        ready_core = build(AgentConfig(
            stripe_provider=stripe, catalog=approved_catalog(),
            catalog_sha256=CATALOG_SHA))
        listed = ready_core.list_plans()
        taxcredit = next(
            plan for plan in listed["plans"]
            if plan["id"] == "taxcredit-seat")
        self.assertEqual(taxcredit["checkout_status"], "ready")
        self.assertFalse(taxcredit["configuration_required"])
        ghg = next(plan for plan in listed["plans"] if plan["id"] == "ghg-seat")
        self.assertEqual(ghg["checkout_status"], "configuration_required")
        self.assertTrue(ghg["configuration_required"])
        encoded = json.dumps(listed, sort_keys=True)
        self.assertNotIn("stripe_provider", encoded)
        self.assertNotIn("sk_live_", encoded)

        # Returned annotations are copies, not additions to the versioned pack.
        taxcredit["checkout_status"] = "tampered"
        reread = ready_core.get_plan("taxcredit-seat")["plan"]
        self.assertEqual(reread["checkout_status"], "ready")
        self.assertNotIn("checkout_status", PLAN_CATALOG["plans"][0])
        self.assertNotIn("configuration_required", PLAN_CATALOG["plans"][0])
        self.assertEqual(PLAN_CATALOG, bundled_before)
        self.assertEqual(build().catalog_sha256, PLAN_CATALOG_SHA256)
        self.assertEqual(draft["plan_catalog_sha256"], PLAN_CATALOG_SHA256)
        self.assertEqual(
            run(no_provider.health())["checks"]["checkout_ready_plans"], 0)
        self.assertEqual(
            run(ready_core.health())["checks"]["checkout_ready_plans"], 1)

    def test_versions_and_bad_input_never_escape_process(self):
        core = build()
        for bad in (None, [], "x", {}, {"action": "unknown"}):
            result = run(core.process(bad))
            self.assertEqual(result["status"], "error")
        health = run(core.health())
        self.assertEqual(core.describe()["version"], VERSION)
        self.assertEqual(health["version"], VERSION)


if __name__ == "__main__":
    unittest.main()
