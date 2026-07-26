import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adapters.market_seller import (
    CASH_ESCROW_ENDPOINT,
    PAYEE_ID,
    SELLER_ID,
    HiveMarketSeller,
    MarketSigner,
    SellerWorkerError,
    _canonical_action,
    _decode_mcp_response,
    default_market_call,
)


NOW = datetime(2026, 7, 26, 9, 30, tzinfo=timezone.utc)


def work(work_id="work_external123", **updates):
    item = {
        "work_id": work_id,
        "buyer_id": "external-buyer",
        "title": "Reviewed multi-agent synthesis",
        "description": "Analyze the supplied problem with independent solvers.",
        "required_capabilities": [
            "multi-agent-synthesis", "cross-review"],
        "budget_minor": 500,
        "currency": "USD",
        "allowed_rails": ["viridis_cash_escrow"],
        "delivery_deadline": (NOW + timedelta(hours=3)).isoformat(),
        "status": "OPEN",
        "funding_status": "UNVERIFIED",
        "match_score": 20,
    }
    item.update(updates)
    return item


class FakeMarket:
    def __init__(self, works, details=None):
        self.works = works
        self.details = details or {}
        self.calls = []

    def __call__(self, tool, arguments):
        self.calls.append((tool, arguments))
        if tool == "search_work":
            return {"status": "ok", "data": {
                "count": len(self.works), "results": self.works}}
        if tool == "get_work":
            return {"status": "ok", "data": self.details.get(
                arguments["work_id"], {
                    **next(item for item in self.works
                           if item["work_id"] == arguments["work_id"]),
                    "offers": [],
                })}
        if tool == "submit_offer":
            return {"status": "ok", "data": {
                "offer_id": "offer_hive123",
                "work_id": arguments["work_id"],
                "seller_id": arguments["seller_id"],
                "amount_minor": arguments["amount_minor"],
                "currency": arguments["currency"],
                "settlement": arguments["settlement"],
                "status": "SUBMITTED",
            }}
        raise AssertionError(tool)


def test_scan_is_read_only_and_labels_open_work_as_not_revenue(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-readiness-only")
    market = FakeMarket([work()])
    report = HiveMarketSeller(
        market, now_fn=lambda: NOW).run_once()

    assert report["mode"] == "read_only"
    assert report["send_attempted"] is False
    assert report["eligible_count"] == 1
    assert "not funded demand or revenue" in report["commercial_boundary"]
    assert [name for name, _ in market.calls] == [
        "search_work", "get_work"]


@pytest.mark.parametrize(("updates", "reason"), [
    ({"buyer_id": "viridis-internal-buyer"},
     "common_control_or_invalid_buyer"),
    ({"required_capabilities": ["carbon"]}, "capability_mismatch"),
    ({"budget_minor": 499}, "budget_below_fixed_price"),
    ({"allowed_rails": ["x402"]}, "verified_cash_escrow_not_allowed"),
    ({"currency": "USDC"}, "currency_not_supported"),
    ({"delivery_deadline": (NOW + timedelta(minutes=30)).isoformat()},
     "delivery_window_too_short"),
    ({"description": ""}, "problem_statement_out_of_bounds"),
])
def test_scan_refuses_unsafe_or_unprofitable_work(
        monkeypatch, updates, reason):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-readiness-only")
    report = HiveMarketSeller(
        FakeMarket([work(**updates)]),
        now_fn=lambda: NOW).scan()
    assert report["eligible_count"] == 0
    assert report["decisions"][0]["refusal_reason"] == reason


def test_scan_refuses_when_provider_is_not_ready(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    report = HiveMarketSeller(
        FakeMarket([work()]), now_fn=lambda: NOW).scan()
    assert report["decisions"][0]["refusal_reason"] == \
        "solver_provider_not_ready"


def test_scan_refuses_duplicate_offer(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-readiness-only")
    item = work()
    market = FakeMarket([item], details={
        item["work_id"]: {**item, "offers": [{"seller_id": SELLER_ID}]}})
    report = HiveMarketSeller(
        market, now_fn=lambda: NOW).scan()
    assert report["decisions"][0]["refusal_reason"] == \
        "offer_already_exists"


def test_apply_requires_separate_environment_gate(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-readiness-only")
    monkeypatch.delenv("HIVE_MARKET_APPLY", raising=False)
    market = FakeMarket([work()])
    report = HiveMarketSeller(
        market, now_fn=lambda: NOW).run_once(apply=True)
    assert report["mode"] == "apply_refused"
    assert report["send_attempted"] is False
    assert "submit_offer" not in [name for name, _ in market.calls]


def test_apply_signs_one_exact_fixed_cash_offer_without_execution(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-readiness-only")
    monkeypatch.setenv("HIVE_MARKET_APPLY", "1")
    private = Ed25519PrivateKey.generate()
    market = FakeMarket([
        work("work_best123", match_score=30),
        work("work_second123", match_score=10),
    ])
    report = HiveMarketSeller(
        market, signer=MarketSigner(private),
        now_fn=lambda: NOW).run_once(apply=True)

    submit_calls = [
        args for name, args in market.calls if name == "submit_offer"]
    assert len(submit_calls) == 1
    submitted = submit_calls[0]
    assert submitted["work_id"] == "work_best123"
    assert submitted["amount_minor"] == 500
    assert submitted["settlement"] == {
        "rail": "viridis_cash_escrow",
        "payment_endpoint": CASH_ESCROW_ENDPOINT,
        "payee_id": PAYEE_ID,
    }
    auth = submitted["auth"]
    body = {
        key: value for key, value in submitted.items()
        if key not in {"seller_id", "auth"}}
    signature = base64.urlsafe_b64decode(
        auth["signature"] + "=" * (-len(auth["signature"]) % 4))
    private.public_key().verify(
        signature,
        _canonical_action(
            "submit_offer", SELLER_ID, auth["nonce"],
            auth["signed_at"], body).encode())
    assert report["send_attempted"] is True
    assert report["execution_started"] is False
    assert report["funding_claimed"] is False
    assert report["money_movement"] == "none"


def test_no_eligible_work_never_loads_signer(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("HIVE_MARKET_APPLY", "1")
    monkeypatch.delenv(
        "VIRIDIS_AGENT_MARKET_PRIVATE_KEY_B64", raising=False)
    report = HiveMarketSeller(
        FakeMarket([work()]), now_fn=lambda: NOW).run_once(apply=True)
    assert report["result"] == "no_eligible_work"
    assert report["send_attempted"] is False


def test_transport_refuses_non_allowlisted_market_url():
    with pytest.raises(SellerWorkerError, match="not allowlisted"):
        default_market_call(
            "search_work", {}, market_url="https://attacker.example/mcp")


def test_mcp_response_parser_accepts_structured_json_and_sse():
    structured = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "result": {"structuredContent": {
            "status": "ok", "data": {"count": 0}}}})
    assert _decode_mcp_response(
        "application/json", structured)["status"] == "ok"
    event = "event: message\ndata: " + structured + "\n\n"
    assert _decode_mcp_response(
        "text/event-stream", event)["data"]["count"] == 0
