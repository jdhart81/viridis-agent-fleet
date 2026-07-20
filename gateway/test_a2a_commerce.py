#!/usr/bin/env python3
"""AC1-AC6: A2A discovery, paid task flow, and fail-closed posture."""
import asyncio
import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a2a_commerce                                             # noqa: E402
import x402_http                                                # noqa: E402
import x402_rail                                                # noqa: E402
import x402_v2                                                  # noqa: E402
from payment_gate import GATE_ATTR                              # noqa: E402
from state_store import StateStore                              # noqa: E402


class Request:
    def __init__(self, body=None, headers=None, task_id=""):
        self._body = body or {}
        self.headers = headers or {}
        self.path_params = {"id": task_id}

    async def json(self):
        return self._body


class Core:
    def __init__(self):
        self.calls = []
        setattr(self, GATE_ATTR, {"consumed_x402": {}})
        self._gate_inner = self.process

    def process(self, payload):
        self.calls.append(payload)
        return {"status": "success", "received": payload}


def run(call):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(call)
    finally:
        loop.close()


def body(response):
    return json.loads(response.body)


def arm(monkeypatch):
    monkeypatch.setenv("X402_ENABLED", "1")
    monkeypatch.setenv("X402_V2_ENABLED", "1")
    monkeypatch.setenv("VIRIDIS_X402_ADDRESS", "0xViridis")
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://fac.test")
    monkeypatch.setenv("X402_V2_NETWORK", x402_v2.BASE_MAINNET_CAIP2)
    monkeypatch.setenv("X402_V2_ASSET", x402_rail.BASE_MAINNET_USDC)
    monkeypatch.delenv("X402_INTRO_ENABLED", raising=False)


def request_body(task_id="", payload=None, args=None):
    message = {
        "messageId": "msg-1" if not task_id else "msg-2",
        "role": "ROLE_USER",
        "parts": [{"data": {
            "skillId": "regulatory-radar.scan_regulations",
            "input": args or {"jurisdiction": "EU", "sector": "energy"},
        }}],
    }
    if task_id:
        message["taskId"] = task_id
        message["parts"] = [{"text": "payment authorization"}]
        message["metadata"] = {
            "x402.payment.status": "payment-submitted",
            "x402.payment.payload": payload,
        }
    return {"message": message}


def extension_headers():
    return {"a2a-extensions": a2a_commerce.EXTENSION_URI}


def signed(requirement, nonce="0x" + "ab" * 32):
    return {
        "x402Version": 2,
        "resource": requirement["resource"],
        "accepted": requirement["accepts"][0],
        "payload": {
            "signature": "0xsigned",
            "authorization": {
                "from": "0xBuyer", "to": "0xViridis",
                "value": requirement["accepts"][0]["amount"],
                "validAfter": "0", "validBefore": "9999999999",
                "nonce": nonce,
            },
        },
        "extensions": requirement["extensions"],
    }


class Facilitator:
    def __init__(self, valid=True, settled=True):
        self.valid = valid
        self.settled = settled
        self.calls = []

    def __call__(self, url, envelope, config):
        phase = url.rsplit("/", 1)[-1]
        self.calls.append(phase)
        ext = base64.b64encode(json.dumps(
            {"bazaar": {"status": "accepted"}}).encode()).decode()
        if phase == "verify":
            return ({"isValid": self.valid,
                     "invalidReason": None if self.valid else "bad_signature"},
                    {"extension-responses": ext})
        return ({"success": self.settled,
                 "errorReason": None if self.settled else "failed",
                 "transaction": "0xa2asettled" if self.settled else ""},
                {"extension-responses": ext})


def build(tmp_path):
    core = Core()
    cores = {"regulatory-radar": core}
    store = StateStore(str(tmp_path / "state.db"))
    return (*a2a_commerce.make_a2a_handlers(
        cores, store, "https://mcp.test"), core, store, cores)


def test_agent_card_is_a2a_1_and_declares_required_x402():
    card = a2a_commerce.agent_card("https://mcp.test")
    assert card["supportedInterfaces"] == [{
        "url": "https://mcp.test/a2a", "protocolBinding": "HTTP+JSON",
        "protocolVersion": "1.0"}]
    assert card["capabilities"]["extensions"][0] == {
        "uri": a2a_commerce.EXTENSION_URI,
        "description": "x402 v2 exact settlement on Base mainnet USDC; settle before serve.",
        "required": True, "params": {"x402Version": 2}}
    assert len(card["skills"]) == 5
    assert all(skill["metadata"]["amountAtomicUsdc"] for skill in card["skills"])


def test_missing_extension_and_kill_switch_fail_before_task(tmp_path, monkeypatch):
    arm(monkeypatch)
    _, send, _, core, _, _ = build(tmp_path)
    missing = run(send(Request(request_body())))
    assert missing.status_code == 400 and core.calls == []
    monkeypatch.setenv("X402_V2_ENABLED", "0")
    disabled = run(send(Request(request_body(), extension_headers())))
    assert disabled.status_code == 503 and core.calls == []


def test_payment_task_persists_then_settles_before_one_execution(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = Facilitator()
    monkeypatch.setattr(x402_v2, "_facilitator_post", fake)
    _, send, get_task, core, store, cores = build(tmp_path)
    challenge = run(send(Request(request_body(), extension_headers())))
    assert challenge.status_code == 200 and core.calls == []
    task = body(challenge)["task"]
    assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    required = task["status"]["message"]["metadata"]["x402.payment.required"]
    assert required["accepts"][0]["amount"] == "250000"
    payload = signed(required)
    completed = run(send(Request(
        request_body(task["id"], payload), extension_headers())))
    result = body(completed)["task"]
    assert result["status"]["state"] == "TASK_STATE_COMPLETED"
    assert result["artifacts"][0]["parts"][0]["data"]["status"] == "success"
    assert fake.calls == ["verify", "settle"] and len(core.calls) == 1
    record = next(iter(getattr(core, GATE_ATTR)["consumed_x402"].values()))
    assert record["surface"] == "a2a-x402-v2"
    assert record["tx_hash"] == "0xa2asettled"
    polled = run(get_task(Request(task_id=task["id"])))
    assert body(polled)["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    replay = run(send(Request(
        request_body(task["id"], payload), extension_headers())))
    assert body(replay)["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert fake.calls == ["verify", "settle"] and len(core.calls) == 1
    restored = Core()
    assert store.restore("regulatory-radar", restored)
    assert getattr(restored, GATE_ATTR)[a2a_commerce.TASKS_KEY][task["id"]][
        "status"]["state"] == "TASK_STATE_COMPLETED"
    metrics = x402_http.settlement_metrics({
        "regulatory-radar": getattr(core, GATE_ATTR)})["total"]
    assert metrics["external_settlements"] == 1


def test_verify_failure_and_bad_schema_never_execute(tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = Facilitator(valid=False)
    monkeypatch.setattr(x402_v2, "_facilitator_post", fake)
    _, send, _, core, _, _ = build(tmp_path)
    invalid = run(send(Request(request_body(args={"sector": "energy"}),
                               extension_headers())))
    assert invalid.status_code == 400 and core.calls == []
    challenge = run(send(Request(request_body(), extension_headers())))
    task = body(challenge)["task"]
    required = task["status"]["message"]["metadata"]["x402.payment.required"]
    failed = run(send(Request(request_body(task["id"], signed(required)),
                              extension_headers())))
    assert failed.status_code == 402
    assert fake.calls == ["verify"] and core.calls == []


def test_task_response_echoes_current_and_extension_headers(tmp_path, monkeypatch):
    arm(monkeypatch)
    card, send, _, _, _, _ = build(tmp_path)
    response = run(card(Request()))
    assert response.media_type == a2a_commerce.MEDIA_TYPE
    assert response.headers["a2a-version"] == "1.0"
    assert response.headers["a2a-extensions"] == a2a_commerce.EXTENSION_URI
    challenge = run(send(Request(request_body(), {
        "x-a2a-extensions": a2a_commerce.EXTENSION_URI})))
    assert challenge.status_code == 200
