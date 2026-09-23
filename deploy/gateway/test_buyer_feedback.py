"""Buyer feedback is token-bound, durable, exactly once, and non-revenue."""
import asyncio
import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import x402_http  # noqa: E402
from payment_gate import GATE_ATTR  # noqa: E402
from state_store import StateStore  # noqa: E402


class Core:
    pass


class Request:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


def run(handler, payload):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(handler(Request(payload)))
    finally:
        loop.close()


def body(response):
    return json.loads(response.body.decode("utf-8"))


def rig(tmp_path):
    token = "feedback-token-with-more-than-thirty-two-characters"
    core = Core()
    setattr(core, GATE_ATTR, {"consumed_x402": {
        "v2:paid": {
            "surface": "http-402-v2",
            "classification_version": 1,
            "route": "regulatory-radar/scan_regulations",
            "payer_wallet": "0xExternal",
            "self_settle": False,
            "amount_atomic": "250000",
            "tx_hash": "0xpaid",
            "timestamp": "2026-08-28T00:00:00+00:00",
            "delivery_status": "delivered",
            "feedback_token_sha256": hashlib.sha256(
                token.encode("utf-8")).hexdigest(),
        },
    }})
    store = StateStore(str(tmp_path / "feedback.db"))
    handler = x402_http.make_buyer_feedback_route(
        {"regulatory-radar": core}, store)
    return token, core, store, handler


def feedback(token, **overrides):
    payload = {
        "feedback_token": token,
        "outcome": "USEFUL",
        "would_buy_again": True,
        "reason_code": "actionable",
        "idempotency_key": "buyer-job-123-feedback",
    }
    payload.update(overrides)
    return payload


def test_feedback_is_durable_bounded_and_visible_in_external_metrics(tmp_path):
    token, core, store, handler = rig(tmp_path)
    response = run(handler, feedback(token))
    assert response.status_code == 201
    result = body(response)
    assert result["status"] == "RECORDED"
    assert result["feedback"]["classification"] == (
        "buyer_possession_feedback")
    assert result["feedback"]["independently_verified"] is False
    assert result["feedback"]["revenue_signal"] is False
    record = next(iter(getattr(core, GATE_ATTR)["consumed_x402"].values()))
    assert record["buyer_feedback"]["outcome"] == "USEFUL"
    metrics = x402_http.settlement_metrics({
        "regulatory-radar": getattr(core, GATE_ATTR),
    })["total"]
    assert metrics["external_buyer_feedback"] == 1
    assert metrics["external_buyer_feedback_useful"] == 1
    assert metrics["external_would_buy_again"] == 1
    assert store.status()["available"] is True


def test_same_feedback_replays_but_changed_feedback_is_rejected(tmp_path):
    token, _, store, handler = rig(tmp_path)
    first = run(handler, feedback(token))
    replay = run(handler, feedback(token))
    changed = run(handler, feedback(token, outcome="NOT_USEFUL"))
    assert first.status_code == 201
    assert replay.status_code == 200
    assert body(replay)["idempotent_replay"] is True
    assert changed.status_code == 409
    assert body(changed)["status"] == "ALREADY_RECORDED"
    store.close()


def test_unknown_token_and_unbounded_payload_fail_closed(tmp_path):
    token, _, store, handler = rig(tmp_path)
    missing = run(handler, feedback("x" * 40))
    assert missing.status_code == 404
    assert body(missing)["feedback_recorded"] is False

    invalid = run(handler, feedback(token, would_buy_again="yes"))
    assert invalid.status_code == 400
    assert body(invalid)["status"] == "INVALID_REQUEST"
    store.close()
