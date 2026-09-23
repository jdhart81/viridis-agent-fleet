"""Gateway integration tests for account attribution + seat entitlements.

These tests intentionally isolate the three-way billing decision from Stripe:
the subscriptions core owns Stripe verification; PaymentGate consumes only its
already-verified reservation contract and must durably finalize every token.
Stdlib unittest compatible.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

import sys
sys.path.insert(0, str(HERE))

from account_auth import (AccountContextMiddleware, account_key_context,
                          current_account_key)
from payment_gate import GATE_ATTR, PRICE_MINOR, PaymentGate
from state_store import StateStore
from viridis_mcp_gateway import _attach_subscription_bearer


def call(core, payload):
    result = core.process(payload)
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


def load_subscription_core_module():
    name = "gateway_test_subscriptions_core"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "subscriptions-agent" / "src" / "core.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ServiceCore:
    """Small sync sellable core; exercises PaymentGate's sync convention."""

    KNOWN_ACTIONS = frozenset({"calculate"})
    READ_ACTIONS = frozenset()

    def __init__(self):
        self.calls = 0

    def process(self, payload):
        self.calls += 1
        return {"status": "ok", "data": {"calls": self.calls,
                                            "payload": deepcopy(payload)}}


class MeterCore:
    def __init__(self):
        self.meters = {}
        self.sequence = 0

    async def process(self, payload):
        action = payload.get("action")
        if action == "create_meter":
            self.sequence += 1
            meter_id = f"meter-{self.sequence}"
            self.meters[meter_id] = {
                "price": payload["price_minor_per_unit"], "events": []}
            return {"status": "ok", "data": {"meter_id": meter_id}}
        if action == "record_usage":
            self.meters[payload["meter_id"]]["events"].append(deepcopy(payload))
            return {"status": "ok", "data": {"recorded": True}}
        if action == "close_period":
            meter = self.meters[payload["meter_id"]]
            amount = len(meter["events"]) * meter["price"]
            return {"status": "ok", "data": {"amount_minor": amount}}
        raise AssertionError(f"unexpected meter action: {action}")


class SubscriptionContract:
    """Minimal implementation of the core's reservation protocol."""

    def __init__(self, decisions=None, *, raise_on_reserve=False):
        self.account_id = "acct-test"
        self.account_key = "vir_acct_test_key"
        self.decisions = list(decisions or [])
        self.raise_on_reserve = raise_on_reserve
        self.reserve_calls = 0
        self.state_version = 0
        self.open_tokens = {}
        self.commits = 0
        self.rollbacks = 0

    def resolve_account_key(self, key):
        return self.account_id if key == self.account_key else None

    def reserve_entitlement(self, account_id, agent_id, request_id,
                            per_call_price_minor):
        self.reserve_calls += 1
        if self.raise_on_reserve:
            raise RuntimeError("lookup unavailable")
        decision = deepcopy(self.decisions.pop(0))
        decision.setdefault("request_id", request_id)
        decision.setdefault("account_id", account_id)
        decision.setdefault("agent_id", agent_id)
        decision.setdefault("catalog", {
            "version": "0.1.0", "sha256": "a" * 64})
        if decision.pop("with_token", True):
            self.state_version += 1
            token = f"reservation-{self.state_version}"
            self.open_tokens[token] = self.state_version
            decision["reservation_token"] = token
            decision["durability_required"] = True
        else:
            decision["reservation_token"] = None
            decision["durability_required"] = False
        return decision

    def commit_reservation(self, token):
        if token not in self.open_tokens:
            return False
        self.open_tokens.pop(token)
        self.commits += 1
        return True

    def rollback_reservation(self, token):
        if token not in self.open_tokens:
            return False
        self.open_tokens.pop(token)
        self.state_version -= 1
        self.rollbacks += 1
        return True


class SaveFailStore(StateStore):
    def save(self, name, core):
        if name == "subscriptions":
            return False
        return super().save(name, core)


class GroupSaveFailStore(StateStore):
    def save_many(self, cores):
        return False


def included():
    return {"path": "included_quota_waiver", "entitled": True,
            "waive_per_call_charge": True,
            "should_run_per_call_gate": False,
            "bypass_anonymous_freemium": False,
            "requires_direct_overage_charge": False,
            "overage_minor": 0}


def overage():
    return {"path": "overage_meter", "entitled": True,
            "waive_per_call_charge": False,
            "should_run_per_call_gate": True,
            "bypass_anonymous_freemium": True,
            "requires_direct_overage_charge": True,
            "overage_minor": PRICE_MINOR["smartscale"]}


def fallback(*, with_token=False):
    return {"path": "per_call_fallback", "entitled": False,
            "waive_per_call_charge": False,
            "should_run_per_call_gate": True,
            "bypass_anonymous_freemium": False,
            "requires_direct_overage_charge": False,
            "reason": "no_active_covering_subscription",
            "with_token": with_token}


class SubscriptionGateIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, subscriptions, *, free=10, store_cls=StateStore,
              key_getter=None):
        store = store_cls(Path(self.tmp.name) / "state.db")
        service, meter = ServiceCore(), MeterCore()
        store.attach("smartscale", service)
        gate = PaymentGate(
            store, meter, free_calls_per_day=free,
            subscription_core=subscriptions,
            account_key_getter=(key_getter or current_account_key),
            request_id_factory=lambda: f"request-{subscriptions.reserve_calls + 1}")
        gate.attach("smartscale", service)
        return store, gate, service, meter

    def test_included_quota_waives_without_consuming_daily_free_or_credit(self):
        subscriptions = SubscriptionContract([included()])
        store, _, service, meter = self.build(subscriptions, free=0)
        try:
            with account_key_context(subscriptions.account_key):
                result = call(service, {"action": "calculate"})
            gate_state = getattr(service, GATE_ATTR)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(gate_state["used"], 0)
            self.assertEqual(gate_state["credits"], 0)
            self.assertEqual(gate_state["subscription_waived"], 1)
            self.assertEqual(subscriptions.commits, 1)
            self.assertEqual(subscriptions.rollbacks, 0)
            seat_meter = meter.meters[gate_state["subscription_meter_id"]]
            self.assertEqual(seat_meter["price"], 0)
            self.assertEqual(len(seat_meter["events"]), 1)
        finally:
            store.close()

    def test_overage_bypasses_anonymous_free_and_returns_exact_per_call_402(self):
        subscriptions = SubscriptionContract([overage()])
        store, _, service, meter = self.build(subscriptions, free=10)
        try:
            with account_key_context(subscriptions.account_key):
                result = call(service, {"action": "calculate"})
            gate_state = getattr(service, GATE_ATTR)
            self.assertEqual(result["error_type"], "payment_required")
            self.assertEqual(result["billing_path"], "subscription_overage")
            self.assertEqual(result["amount_minor"], PRICE_MINOR["smartscale"])
            self.assertEqual(gate_state["used"], 0)
            self.assertEqual(service.calls, 0)
            self.assertEqual(subscriptions.commits, 0)
            self.assertEqual(subscriptions.rollbacks, 1)
            self.assertEqual(subscriptions.state_version, 0)
            self.assertEqual(subscriptions.open_tokens, {})
            paid_meter = meter.meters[gate_state["meter_id"]]
            self.assertEqual(paid_meter["price"], PRICE_MINOR["smartscale"])
        finally:
            store.close()

    def test_overage_consumes_one_prepaid_credit_and_serves_once(self):
        subscriptions = SubscriptionContract([overage()])
        store, gate, service, _ = self.build(subscriptions, free=10)
        try:
            getattr(service, GATE_ATTR)["credits"] = 1
            with account_key_context(subscriptions.account_key):
                result = call(service, {"action": "calculate"})
            self.assertEqual(result["status"], "ok")
            self.assertEqual(service.calls, 1)
            self.assertEqual(getattr(service, GATE_ATTR)["credits"], 0)
            self.assertEqual(getattr(service, GATE_ATTR)["used"], 0)
            self.assertEqual(gate.status()["subscription_entitlements"]["errors"], {})
        finally:
            store.close()

    def test_lookup_error_falls_through_to_freemium_exactly_once(self):
        subscriptions = SubscriptionContract(raise_on_reserve=True)
        store, gate, service, _ = self.build(subscriptions, free=1)
        try:
            with account_key_context(subscriptions.account_key):
                first = call(service, {"action": "calculate"})
                second = call(service, {"action": "calculate"})
            self.assertEqual(first["status"], "ok")
            self.assertEqual(second["error_type"], "payment_required")
            self.assertEqual(service.calls, 1)
            self.assertEqual(getattr(service, GATE_ATTR)["used"], 1)
            self.assertEqual(subscriptions.reserve_calls, 2)
            self.assertIn("smartscale",
                          gate.status()["subscription_entitlements"]["errors"])
        finally:
            store.close()

    def test_fallback_with_lifecycle_reservation_is_committed_before_freemium(self):
        subscriptions = SubscriptionContract([fallback(with_token=True)])
        store, _, service, _ = self.build(subscriptions, free=1)
        try:
            with account_key_context(subscriptions.account_key):
                result = call(service, {"action": "calculate"})
            self.assertEqual(result["status"], "ok")
            self.assertEqual(subscriptions.commits, 1)
            self.assertEqual(subscriptions.open_tokens, {})
            self.assertEqual(getattr(service, GATE_ATTR)["used"], 1)
        finally:
            store.close()

    def test_failed_subscription_save_rolls_back_then_uses_freemium(self):
        subscriptions = SubscriptionContract([included()])
        store, gate, service, _ = self.build(
            subscriptions, free=1, store_cls=SaveFailStore)
        try:
            with account_key_context(subscriptions.account_key):
                result = call(service, {"action": "calculate"})
            self.assertEqual(result["status"], "ok")
            self.assertEqual(subscriptions.commits, 0)
            self.assertEqual(subscriptions.rollbacks, 1)
            self.assertEqual(subscriptions.state_version, 0)
            self.assertEqual(getattr(service, GATE_ATTR)["used"], 1)
            self.assertEqual(
                gate.status()["subscription_entitlements"]["errors"]
                    ["smartscale"],
                "durability: save_failed")
        finally:
            store.close()

    def test_ambiguous_or_wrong_price_decision_never_grants_seat_access(self):
        malformed = overage()
        malformed["overage_minor"] = PRICE_MINOR["smartscale"] + 1
        subscriptions = SubscriptionContract([malformed])
        store, _, service, _ = self.build(subscriptions, free=1)
        try:
            with account_key_context(subscriptions.account_key):
                result = call(service, {"action": "calculate"})
            # The reservation is finalized, but an inconsistent core envelope
            # is never interpreted optimistically; normal freemium runs once.
            self.assertEqual(result["status"], "ok")
            self.assertEqual(getattr(service, GATE_ATTR)["used"], 1)
            self.assertEqual(getattr(service, GATE_ATTR)["subscription_overage"], 0)
            self.assertEqual(subscriptions.commits, 0)
            self.assertEqual(subscriptions.rollbacks, 1)
        finally:
            store.close()

    def test_failed_atomic_overage_save_restores_credit_and_refuses_service(self):
        subscriptions = SubscriptionContract([overage()])
        store, gate, service, _ = self.build(
            subscriptions, free=10, store_cls=GroupSaveFailStore)
        try:
            getattr(service, GATE_ATTR)["credits"] = 1
            with account_key_context(subscriptions.account_key):
                result = call(service, {"action": "calculate"})
            gate_state = getattr(service, GATE_ATTR)
            self.assertEqual(result["error_type"], "payment_required")
            self.assertEqual(result["billing_path"], "subscription_overage")
            self.assertEqual(service.calls, 0)
            self.assertEqual(gate_state["credits"], 1)
            self.assertEqual(gate_state["used"], 0)
            self.assertEqual(gate_state["subscription_overage"], 0)
            self.assertEqual(subscriptions.state_version, 0)
            self.assertEqual(subscriptions.commits, 0)
            self.assertEqual(subscriptions.rollbacks, 1)
            self.assertEqual(
                gate.status()["subscription_entitlements"]["errors"]
                    ["smartscale"],
                "durability: group_save_failed")
        finally:
            store.close()

    def test_anonymous_and_unknown_bearer_preserve_existing_freemium(self):
        subscriptions = SubscriptionContract([])
        store, _, service, _ = self.build(subscriptions, free=1)
        try:
            anonymous = call(service, {"action": "calculate"})
            with account_key_context("unknown-key"):
                refused = call(service, {"action": "calculate"})
            self.assertEqual(anonymous["status"], "ok")
            self.assertEqual(refused["error_type"], "payment_required")
            self.assertEqual(subscriptions.reserve_calls, 0)
        finally:
            store.close()


class RealCoreAtomicIntegration(unittest.TestCase):
    def test_refused_real_core_overage_rolls_back_then_credit_commits_atomically(self):
        module = load_subscription_core_module()
        catalog = deepcopy(module.PLAN_CATALOG)
        for plan in catalog["plans"]:
            if plan["id"] == "taxcredit-seat":
                plan.update({
                    "stripe_price_id": "price_TaxCreditSeat149",
                    "approval_status": "approved",
                    "checkout_enabled": True,
                    "coverage_ready": True,
                    "included_calls_per_month": 1,
                })
        catalog["configuration_notice"] = "gateway atomic integration"
        catalog_sha = "c" * 64
        account_ref = "atomic-buyer@example.test"
        verified = {
            "status": "ok", "verified": True, "mode": "subscription",
            "line_item_count": 1, "subscription_id": "sub_AtomicSeat001",
            "customer_id": "cus_AtomicBuyer001", "subscription_status": "active",
            "current_period_start": 1782864000,
            "current_period_end": 1785542400,
            "price_id": "price_TaxCreditSeat149", "quantity": 1,
            "unit_amount": 14900, "currency": "usd", "interval": "month",
            "interval_count": 1, "price_active": True,
            "plan_id": "taxcredit-seat",
            "catalog_version": catalog["pack_version"],
            "catalog_sha256": catalog_sha, "account_ref": account_ref,
            "livemode": True,
        }

        class Provider:
            def verify_subscription(self, _reference):
                return deepcopy(verified)

        config = module.AgentConfig(
            stripe_provider=Provider(), catalog=catalog,
            catalog_sha256=catalog_sha,
            clock=lambda: datetime.fromisoformat("2026-07-15T12:00:00+00:00"),
            key_factory=lambda: "vir_acct_" + "z" * 48)
        subscriptions = module.build(config)
        account = subscriptions.create_account(account_ref)
        subscriptions.record_subscription("sub_AtomicSeat001")

        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "atomic.db")
            service, meter = ServiceCore(), MeterCore()
            store.attach("taxcredit-engine", service)
            self.assertTrue(store.save("subscriptions", subscriptions))
            gate = PaymentGate(
                store, meter, free_calls_per_day=10,
                subscription_core=subscriptions,
                account_key_getter=lambda: account["account_key"],
                request_id_factory=iter(
                    ("included", "refused-overage", "paid-overage")).__next__)
            gate.attach("taxcredit-engine", service)

            first = call(service, {"action": "calculate"})
            refused = call(service, {"action": "calculate"})
            after_refusal = subscriptions.usage_summary(
                account["account_id"], account["account_key"])
            self.assertEqual(first["status"], "ok")
            self.assertEqual(refused["error_type"], "payment_required")
            self.assertEqual(after_refusal["totals"]["included_used"], 1)
            self.assertEqual(after_refusal["totals"]["overage_calls"], 0)
            self.assertEqual(after_refusal["totals"]["overage_minor"], 0)
            self.assertEqual(len(subscriptions._request_decisions), 1)

            getattr(service, GATE_ATTR)["credits"] = 1
            paid = call(service, {"action": "calculate"})
            after_paid = subscriptions.usage_summary(
                account["account_id"], account["account_key"])
            self.assertEqual(paid["status"], "ok")
            self.assertEqual(after_paid["totals"]["overage_calls"], 1)
            self.assertEqual(after_paid["totals"]["overage_minor"], 200)
            self.assertEqual(getattr(service, GATE_ATTR)["credits"], 0)
            self.assertEqual(len(subscriptions._request_decisions), 2)
            store.close()


class BearerIntegration(unittest.TestCase):
    def test_duplicate_authorization_headers_attribute_nothing_and_context_resets(self):
        observed = []

        async def inner(scope, receive, send):
            observed.append(current_account_key())
            await send({"type": "http.response.start", "status": 200,
                        "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def receive():
            return {"type": "http.request", "body": b"",
                    "more_body": False}

        async def send(_message):
            return None

        middleware = AccountContextMiddleware(inner)
        duplicate_scope = {
            "type": "http", "headers": [
                (b"authorization", b"Bearer one"),
                (b"authorization", b"Bearer two")]}
        asyncio.run(middleware(duplicate_scope, receive, send))
        self.assertEqual(observed, [None])
        self.assertIsNone(current_account_key())

    def test_sensitive_payload_key_is_overwritten_by_request_bearer(self):
        class Recorder:
            def __init__(self):
                self.seen = []

            async def process(self, payload):
                self.seen.append(deepcopy(payload))
                return {"status": "ok"}

        core = Recorder()
        _attach_subscription_bearer(core, current_account_key)
        with account_key_context("header-key"):
            asyncio.run(core.process({
                "action": "subscription_status", "account_id": "acct",
                "account_key": "smuggled-key"}))
        self.assertEqual(core.seen[0]["account_key"], "header-key")


class GatewaySurfaceIntegration(unittest.TestCase):
    def test_health_and_directory_mount_subscriptions_outside_22_leaf_agents(self):
        from starlette.testclient import TestClient
        import viridis_mcp_gateway as gateway

        with tempfile.TemporaryDirectory() as tmp:
            old_db = os.environ.get("STATE_DB")
            old_members = gateway.EXTERNAL_MEMBERS
            os.environ["STATE_DB"] = str(Path(tmp) / "gateway.db")
            gateway.EXTERNAL_MEMBERS = []
            try:
                with TestClient(gateway.build_app()) as client:
                    health_response = client.get("/healthz")
                    directory_response = client.get("/")
            finally:
                gateway.EXTERNAL_MEMBERS = old_members
                if old_db is None:
                    os.environ.pop("STATE_DB", None)
                else:
                    os.environ["STATE_DB"] = old_db

        self.assertEqual(health_response.status_code, 200,
                         health_response.text)
        health = health_response.json()
        directory = directory_response.json()
        self.assertEqual(len(health["agents"]), 28)
        self.assertNotIn("subscriptions", health["agents"])
        self.assertEqual(health["subscriptions"]["version"], "0.1.1")
        self.assertTrue(
            health["subscriptions"]["checks"]["stripe_provider_attached"])
        self.assertTrue(
            health["subscriptions"]["checks"]
            ["durable_activation_commit_attached"])
        self.assertIn("plan_mix",
                      health["subscriptions"]["mrr_summary"])
        self.assertEqual(
            health["subscriptions"]["mrr_summary"]["mrr_minor"], 0)
        self.assertTrue(
            health["payment_gate"]["subscription_entitlements"]["enabled"])
        self.assertEqual(
            directory["infrastructure"]["subscriptions"]["endpoint"],
            "/subscriptions/mcp")
        self.assertEqual(len(directory["agents"]), 28)


if __name__ == "__main__":
    unittest.main(verbosity=2)
