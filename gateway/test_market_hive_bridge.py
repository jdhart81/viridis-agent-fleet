import asyncio
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from market_hive_bridge import MarketHiveBridge, PAYEE_ID, SELLER_ID


NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


class Store:
    def __init__(self, durable=True):
        self.durable = durable
        self.saves = []

    def save(self, name, core):
        self.saves.append((name, core.state.copy()))
        return self.durable


class Signer:
    def auth(self, action, actor_id, body):
        assert actor_id == SELLER_ID
        return {
            "nonce": f"nonce-{action}",
            "signed_at": NOW.isoformat(),
            "signature": "signed",
        }


class Gate:
    def __init__(self):
        self.calls = []

    def reserve_market_payment(self, name, binding, payload):
        self.calls.append((name, binding, payload))
        return {
            "status": "ok",
            "token": "market-hold-token",
            "state": "RESERVED",
            "money_movement": "none",
        }


class Hive:
    def __init__(self):
        self.solve_calls = 0
        self.audit_calls = 0

    async def process(self, payload):
        if payload["action"] == "solve":
            self.solve_calls += 1
            assert payload["_market_payment_token"] == "market-hold-token"
            return {
                "status": "ok",
                "data": {
                    "job_id": "hive-job-1",
                    "state": "COMPLETE",
                    "audit_sha256": "a" * 64,
                    "synthesis": {
                        "sections": [{"content": "reviewed answer"}],
                        "energy_j": 1.0,
                    },
                },
            }
        assert payload == {"action": "audit_job", "job_id": "hive-job-1"}
        self.audit_calls += 1
        return {
            "status": "ok",
            "data": {
                "job_id": "hive-job-1",
                "audit_sha256": "a" * 64,
                "lineage": {"reviews": [{"accepted": True}]},
            },
        }


def work_detail(*, funded=True, buyer="external-buyer"):
    receipt = {
        "verified": True,
        "funding_status": "VERIFIED",
        "event_id": "funding_" + "1" * 64,
        "event_sha256": "2" * 64,
        "work_id": "work_external_1",
        "money_primitive": {
            "primitive": "stripe_checkout_escrow_funding",
            "escrow_id": "esc_live_1",
            "escrow_state": "FUNDED",
            "amount_minor": 500,
            "currency": "USD",
            "payer": buyer,
            "payee": PAYEE_ID,
        },
    }
    return {
        "work_id": "work_external_1",
        "buyer_id": buyer,
        "title": "Review this decision",
        "description": "Analyze the supplied decision and produce a reviewed answer.",
        "required_capabilities": ["reviewed-problem-solving"],
        "budget_minor": 500,
        "currency": "USD",
        "allowed_rails": ["viridis_cash_escrow"],
        "delivery_deadline": "2026-07-27T12:00:00+00:00",
        "status": "AWARDED",
        "awarded_offer_id": "offer_hive_1",
        "funding_status": "VERIFIED" if funded else "UNVERIFIED",
        "funding_receipt": receipt if funded else None,
        "offers": [{
            "offer_id": "offer_hive_1",
            "work_id": "work_external_1",
            "seller_id": SELLER_ID,
            "amount_minor": 500,
            "currency": "USD",
            "status": "AWARDED",
            "settlement": {
                "rail": "viridis_cash_escrow",
                "payee_id": PAYEE_ID,
            },
        }],
        "delivery": None,
        "settlement": None,
    }


class Market:
    def __init__(self, detail=None, fail_delivery_once=False):
        self.detail = detail or work_detail()
        self.fail_delivery_once = fail_delivery_once
        self.calls = []
        self.deliveries = []

    def __call__(self, tool, arguments):
        self.calls.append((tool, arguments))
        if tool == "read_agent_inbox":
            return {"status": "ok", "data": {
                "messages": [{
                    "kind": "funding",
                    "work_id": self.detail["work_id"],
                }],
            }}
        if tool == "get_work":
            return {"status": "ok", "data": self.detail}
        if tool == "submit_delivery":
            if self.fail_delivery_once:
                self.fail_delivery_once = False
                raise RuntimeError("temporary Market outage")
            self.deliveries.append(arguments)
            return {"status": "ok", "data": {
                "delivery_id": "delivery_1",
                "work_id": self.detail["work_id"],
                "status": "DELIVERED",
            }}
        raise AssertionError(tool)


def build_bridge(market=None, store=None, hive=None, gate=None):
    return MarketHiveBridge(
        store or Store(),
        hive or Hive(),
        gate or Gate(),
        market_call=market or Market(),
        signer=Signer(),
        now_fn=lambda: NOW,
    )


def test_read_only_mode_has_zero_external_or_model_calls():
    market, hive, gate = Market(), Hive(), Gate()
    bridge = build_bridge(market=market, hive=hive, gate=gate)
    result = asyncio.run(bridge.run_once(apply=False))
    assert result["mode"] == "read_only"
    assert result["execution_started"] is False
    assert market.calls == []
    assert hive.solve_calls == 0
    assert gate.calls == []


def test_unverified_or_related_party_work_never_reserves_or_executes(
        monkeypatch):
    monkeypatch.setenv("HIVE_MARKET_LIFECYCLE_ENABLED", "1")
    for detail in (
            work_detail(funded=False),
            work_detail(buyer="viridis-related-buyer")):
        market, hive, gate = Market(detail), Hive(), Gate()
        bridge = build_bridge(market=market, hive=hive, gate=gate)
        result = asyncio.run(bridge.run_once(apply=True))
        assert result["result"] == "no_verified_funded_hive_work"
        assert hive.solve_calls == 0
        assert gate.calls == []
        assert market.deliveries == []


def test_verified_funding_runs_once_and_delivers_durable_exact_artifact(
        monkeypatch):
    monkeypatch.setenv("HIVE_MARKET_LIFECYCLE_ENABLED", "1")
    market, store, hive, gate = Market(), Store(), Hive(), Gate()
    bridge = build_bridge(
        market=market, store=store, hive=hive, gate=gate)
    result = asyncio.run(bridge.run_once(apply=True))
    assert result["status"] == "ok"
    assert result["escrow_state"] == "FUNDED"
    assert result["money_movement"] == "none before buyer acceptance"
    assert hive.solve_calls == 1
    assert hive.audit_calls == 1
    assert len(gate.calls) == 1
    assert len(market.deliveries) == 1

    submitted = market.deliveries[0]
    digest = submitted["content_sha256"]
    content = bridge.artifact_bytes(digest)
    assert content is not None
    assert hashlib.sha256(content).hexdigest() == digest
    assert submitted["artifact_url"].endswith(f"/{digest}.json")
    assert bridge.state["jobs"]["work_external_1"]["stage"] == "DELIVERED"
    assert all(name == "market_hive_bridge" for name, _ in store.saves)
    forbidden = {"accept_delivery", "attest_settlement",
                 "confirm_work_funding", "submit_usefulness_feedback"}
    assert forbidden.isdisjoint(tool for tool, _ in market.calls)


def test_delivery_retry_reuses_artifact_and_never_reruns_paid_solve(
        monkeypatch):
    monkeypatch.setenv("HIVE_MARKET_LIFECYCLE_ENABLED", "1")
    market, hive = Market(fail_delivery_once=True), Hive()
    bridge = build_bridge(market=market, hive=hive)
    first = asyncio.run(bridge.run_once(apply=True))
    assert first["status"] == "error"
    assert bridge.state["jobs"]["work_external_1"]["stage"] == "ARTIFACT_READY"
    assert hive.solve_calls == 1

    second = asyncio.run(bridge.run_once(apply=True))
    assert second["status"] == "ok"
    assert hive.solve_calls == 1
    assert hive.audit_calls == 1
    assert len(market.deliveries) == 1


def test_bridge_persistence_failure_stops_before_model(monkeypatch):
    monkeypatch.setenv("HIVE_MARKET_LIFECYCLE_ENABLED", "1")
    hive = Hive()
    bridge = build_bridge(store=Store(durable=False), hive=hive)
    result = asyncio.run(bridge.run_once(apply=True))
    assert result["status"] == "error"
    assert "not durable" in result["message"]
    assert hive.solve_calls == 0
