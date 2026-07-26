#!/usr/bin/env python3
"""X2-1..X2-8 — separate HTTP x402 v2/Bazaar lane."""
import asyncio
import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import x402_http                                             # noqa: E402
import x402_rail                                             # noqa: E402
import x402_v2                                               # noqa: E402
from payment_gate import GATE_ATTR                           # noqa: E402
from state_store import StateStore                           # noqa: E402


TEST_TOOLS = {("regulatory-radar", "scan_regulations"): "scan"}
TEST_ARGS = {
    "jurisdiction": "US",
    "sector": "energy",
    "query": "45V clean energy tax credit emissions disclosure",
}
HIVE_ARGS = {
    "problem": "Choose a reviewed industrial energy strategy.",
    "budget_minor": 500,
    "subtasks": ["Assess feasibility.", "Assess economics and risk."],
    "depth": 0,
    "redundancy": 2,
    "accept_threshold": 0.6,
    "seed": 0,
    "fee_bps": 0,
}
V1_RAIL_SHA256 = "ec8bdf03de5394b363627756e8c2c34a72fbf2b40f8af438e513c71c17f9e770"


class FakeRequest:
    def __init__(self, headers=None, body=None, method="POST", query=None,
                 agent="regulatory-radar", tool="scan_regulations"):
        self.path_params = {"agent": agent, "tool": tool}
        self.headers = headers or {}
        self._body = TEST_ARGS if body is None else body
        self.method = method
        self.query_params = query or {}

    async def json(self):
        return self._body


class DummyCore:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []
        setattr(self, GATE_ATTR, {"consumed_x402": {}})
        self._gate_inner = self._run

    def _run(self, payload):
        self.calls.append(payload)
        return {"status": "success", "received": payload}


class FakeFacilitator:
    def __init__(self, verify=True, settle=True, verify_status="processing",
                 settle_status="processing", fail=None):
        self.verify = verify
        self.settle = settle
        self.verify_status = verify_status
        self.settle_status = settle_status
        self.fail = fail
        self.calls = []

    @staticmethod
    def _extension(status):
        payload = {"bazaar": {"status": status}}
        if status == "rejected":
            payload["bazaar"]["rejectedReason"] = "schema invalid"
        return base64.b64encode(json.dumps(payload).encode()).decode()

    def __call__(self, url, body, cfg):
        phase = url.rsplit("/", 1)[-1]
        self.calls.append((phase, body))
        if self.fail == phase:
            raise TimeoutError("facilitator timeout")
        if phase == "verify":
            return ({"isValid": self.verify,
                     "invalidReason": None if self.verify else "invalid_payload"},
                    {"extension-responses": self._extension(
                        self.verify_status)})
        return ({"success": self.settle,
                 "errorReason": None if self.settle else "insufficient_funds",
                 "transaction": "0xv2settled" if self.settle else "",
                 "network": cfg["network"],
                 "amount": body["paymentRequirements"]["amount"]},
                {"extension-responses": self._extension(
                    self.settle_status)})


def arm(monkeypatch, v2=True):
    monkeypatch.setenv("X402_ENABLED", "1")
    monkeypatch.setenv("X402_V2_ENABLED", "1" if v2 else "0")
    monkeypatch.setenv("VIRIDIS_X402_ADDRESS", "0xViridis")
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://fac.test")
    monkeypatch.setenv("X402_V2_NETWORK", x402_v2.BASE_MAINNET_CAIP2)
    monkeypatch.setenv("X402_V2_ASSET", x402_rail.BASE_MAINNET_USDC)
    monkeypatch.delenv("X402_INTRO_ENABLED", raising=False)


def build(tmp_path, core=None, agent="regulatory-radar",
          tool="scan_regulations"):
    store = StateStore(str(tmp_path / "state.db"))
    core = core or DummyCore()
    registry = {(agent, tool): x402_http.X402_HTTP_TOOLS.get(
        (agent, tool), x402_http.AGENT402_HTTP_TOOLS.get(
            (agent, tool), TEST_TOOLS.get((agent, tool))))}
    handler = x402_http.make_x402_http_route(
        {agent: core}, store, "https://mcp.test", tools=registry)
    return handler, core, store


def go(handler, request):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(handler(request))
    finally:
        loop.close()


def body_of(response):
    return json.loads(response.body.decode())


def decode_header(response, name):
    return json.loads(base64.b64decode(response.headers[name]).decode())


def signed_from(challenge, nonce="0x" + "ab" * 32, payer="0xBuyer"):
    required = decode_header(challenge, x402_v2.PAYMENT_REQUIRED_HEADER)
    payload = {
        "x402Version": 2,
        "resource": required["resource"],
        "accepted": required["accepts"][0],
        "payload": {
            "signature": "0xsigned",
            "authorization": {"from": payer, "to": "0xViridis",
                              "value": required["accepts"][0]["amount"],
                              "validAfter": "0", "validBefore": "9999999999",
                              "nonce": nonce},
        },
        "extensions": required["extensions"],
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def install_fake(monkeypatch, fake):
    monkeypatch.setattr(x402_v2, "_facilitator_post", fake)


# X2-1: v1 module frozen and default-off behavior preserved exactly.
def test_X2_1_v1_lane_source_is_byte_untouched():
    digest = hashlib.sha256(Path(x402_rail.__file__).read_bytes()).hexdigest()
    assert digest == V1_RAIL_SHA256


def test_X2_1_flag_off_keeps_wave6_v1_behavior(tmp_path, monkeypatch):
    arm(monkeypatch, v2=False)
    handler, _, _ = build(tmp_path)
    challenge = go(handler, FakeRequest())
    assert challenge.status_code == 402
    assert body_of(challenge)["x402Version"] == 1
    assert x402_v2.PAYMENT_REQUIRED_HEADER not in challenge.headers


# X2-2/X2-8: v2 shape, CAIP network, mainnet token domain, exact price math.
def test_X2_2_mainnet_402_shape_and_usd_coin_domain(tmp_path, monkeypatch):
    arm(monkeypatch)
    handler, _, _ = build(tmp_path)
    response = go(handler, FakeRequest(method="GET", query=TEST_ARGS))
    assert response.status_code == 402 and body_of(response) == {
        "error": "PAYMENT-SIGNATURE required"}
    required = decode_header(response, x402_v2.PAYMENT_REQUIRED_HEADER)
    accepted = required["accepts"][0]
    assert required["x402Version"] == 2
    assert accepted["network"] == "eip155:8453"
    assert accepted["amount"] == "250000"
    assert accepted["extra"] == {"name": "USD Coin", "version": "2"}
    assert required["resource"]["url"].endswith(
        "/x402/regulatory-radar/scan_regulations")


def test_regulatory_radar_fixture_contract_is_publicly_exact():
    metadata = x402_http.X402_HTTP_METADATA[
        ("regulatory-radar", "scan_regulations")]
    assert metadata["input_example"] == TEST_ARGS
    assert metadata["input_schema"]["additionalProperties"] is False
    assert set(metadata["input_schema"]["properties"]) == {
        "jurisdiction", "sector", "query"}
    assert metadata["input_schema"]["properties"]["jurisdiction"]["enum"] == [
        "AU", "CA", "EU", "GLOBAL", "JP", "SG", "UK", "US",
        "au", "ca", "eu", "global", "jp", "sg", "uk", "us",
        "CALIFORNIA", "California", "california", "US-CA", "us-ca",
    ]


def test_v2_rejects_invalid_input_before_quote_payment_or_execution(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    handler, core, store = build(tmp_path)

    refused = go(handler, FakeRequest(body={
        "jurisdiction": "new-york", "sector": "energy"}))

    assert refused.status_code == 400
    assert body_of(refused) == {
        "error": "input does not match advertised schema",
        "error_type": "input_validation_error",
        "payment_required": False,
        "hint": ("jurisdiction must be one of AU, CA (Canada), EU, GLOBAL, "
                 "JP, SG, UK, US, or CALIFORNIA/US-CA"),
    }
    assert x402_v2.PAYMENT_REQUIRED_HEADER not in refused.headers
    assert fake.calls == []
    assert core.calls == []
    assert getattr(core, GATE_ATTR)["consumed_x402"] == {}

    restored = DummyCore()
    assert store.restore("regulatory-radar", restored) is False


def test_v2_valid_advertised_input_still_returns_payment_quote(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    handler, core, _ = build(tmp_path)

    challenge = go(handler, FakeRequest(body=TEST_ARGS))

    assert challenge.status_code == 402
    assert x402_v2.PAYMENT_REQUIRED_HEADER in challenge.headers
    assert core.calls == []


@pytest.mark.parametrize("supplied", [
    "california", "California", "CALIFORNIA", "us-ca", "US-CA",
])
def test_v2_california_aliases_quote_canonical_input(
        tmp_path, monkeypatch, supplied):
    arm(monkeypatch)
    handler, core, _ = build(tmp_path)

    challenge = go(handler, FakeRequest(body={
        "jurisdiction": supplied, "sector": "energy"}))

    assert challenge.status_code == 402
    assert x402_v2.PAYMENT_REQUIRED_HEADER in challenge.headers
    assert core.calls == []


def test_v2_california_paid_execution_uses_canonical_jurisdiction(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    install_fake(monkeypatch, FakeFacilitator())
    handler, core, _ = build(tmp_path)
    request_body = {"jurisdiction": " US-CA ", "sector": "energy"}
    challenge = go(handler, FakeRequest(body=request_body))
    signature = signed_from(challenge)

    paid = go(handler, FakeRequest(
        body=request_body, headers={"payment-signature": signature}))

    assert paid.status_code == 200
    assert core.calls == [{
        "action": "scan", "jurisdiction": "california", "sector": "energy"}]


def test_X2_2_sepolia_retains_usdc_domain(monkeypatch):
    arm(monkeypatch)
    cfg = x402_v2._cfg()
    cfg.update({"network": x402_v2.BASE_SEPOLIA_CAIP2,
                "asset": x402_v2.BASE_SEPOLIA_USDC})
    required = x402_v2.build_payment_required(
        "regulatory-radar", "scan_regulations", 25,
        "https://mcp.test/x402/regulatory-radar/scan_regulations", "GET",
        x402_http.X402_HTTP_METADATA[
            ("regulatory-radar", "scan_regulations")], cfg)
    assert required["accepts"][0]["extra"]["name"] == "USDC"


@pytest.mark.parametrize("minor,atomic", [(1, "10000"), (25, "250000"),
                                            (200, "2000000")])
def test_X2_8_amount_is_always_derived_from_price_minor(monkeypatch, minor, atomic):
    arm(monkeypatch)
    required = x402_v2.build_payment_required(
        "regulatory-radar", "scan_regulations", minor,
        "https://mcp.test/x402/regulatory-radar/scan_regulations", "POST",
        x402_http.X402_HTTP_METADATA[
            ("regulatory-radar", "scan_regulations")])
    assert required["accepts"][0]["amount"] == atomic


# H402-10 / x402-intro-v1: one durable 1c call per signed payer wallet.
def test_wave9_new_wallet_is_quoted_10000_atomic(tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    handler, _, _ = build(tmp_path)
    challenge = go(handler, FakeRequest(headers={
        "x402-payer-address": "0xNewBuyer"}))
    required = decode_header(challenge, x402_v2.PAYMENT_REQUIRED_HEADER)
    assert required["accepts"][0]["amount"] == "10000"
    status = x402_http.intro_status({})
    assert status["enabled"] is True
    assert status["schedule"]["version"] == "x402-intro-v1"


def test_agent402_alias_stays_at_list_price_when_intro_is_enabled(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    handler, _, _ = build(
        tmp_path, tool="scan_regulations_agent402")
    challenge = go(handler, FakeRequest(
        tool="scan_regulations_agent402",
        headers={"x402-payer-address": "0xNewBuyer"}))
    required = decode_header(challenge, x402_v2.PAYMENT_REQUIRED_HEADER)
    assert body_of(challenge) == required
    assert required["accepts"][0]["amount"] == "250000"
    resource = required["resource"]
    assert resource["url"].endswith(
        "/x402/regulatory-radar/scan_regulations_agent402")
    assert resource["serviceName"] == "Viridis Regulatory Radar"
    assert len(resource["serviceName"]) <= 32
    assert resource["serviceName"].isascii()
    assert resource["category"] == "Search"
    assert resource["tags"] == [
        "climate", "energy", "compliance", "regulation", "CSRD"]
    bazaar = required["extensions"]["bazaar"]
    assert bazaar["info"]["input"]["body"] == TEST_ARGS
    assert bazaar["info"]["output"]


def test_hive_stays_full_price_and_preflights_before_settlement(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    core = DummyCore()
    preflights = []
    core._paid_preflight = (
        lambda payload: preflights.append(payload) or None)
    handler, _, _ = build(
        tmp_path, core=core, agent="hive", tool="solve")
    request = FakeRequest(
        agent="hive", tool="solve", body=HIVE_ARGS,
        headers={"x402-payer-address": "0xNewBuyer"})

    challenge = go(handler, request)
    required = decode_header(challenge, x402_v2.PAYMENT_REQUIRED_HEADER)
    assert challenge.status_code == 402
    assert required["accepts"][0]["amount"] == "5000000"
    assert fake.calls == []
    assert core.calls == []

    paid = go(handler, FakeRequest(
        agent="hive", tool="solve", body=HIVE_ARGS,
        headers={"payment-signature": signed_from(
            challenge, payer="0xNewBuyer")}))
    assert paid.status_code == 200
    assert [phase for phase, _ in fake.calls] == ["verify", "settle"]
    assert core.calls == [{"action": "solve", **HIVE_ARGS}]
    assert preflights == [
        {"action": "solve", **HIVE_ARGS},
        {"action": "solve", **HIVE_ARGS},
    ]
    gate = getattr(core, GATE_ATTR)
    assert x402_http.INTRO_SEEN_KEY not in gate
    record = next(iter(gate["consumed_x402"].values()))
    assert record["intro_price_applied"] is False
    assert record["list_price_minor"] == 500


def test_hive_provider_unavailable_before_quote_or_settlement(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    core = DummyCore()
    core._paid_preflight = lambda _payload: {
        "status": "error", "error_type": "ServiceUnavailable",
        "message": "hive solver provider is not configured"}
    handler, _, store = build(
        tmp_path, core=core, agent="hive", tool="solve")

    refused = go(handler, FakeRequest(
        agent="hive", tool="solve", body=HIVE_ARGS))

    assert refused.status_code == 503
    assert body_of(refused)["payment_required"] is False
    assert fake.calls == []
    assert core.calls == []
    restored = DummyCore()
    assert store.restore("hive", restored) is False


def test_wave9_intro_settle_marks_seen_then_quotes_full_price(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "true")
    install_fake(monkeypatch, FakeFacilitator())
    handler, core, _ = build(tmp_path)
    hint = {"x402-payer-address": "0xBuyer"}
    challenge = go(handler, FakeRequest(headers=hint))
    assert decode_header(challenge, x402_v2.PAYMENT_REQUIRED_HEADER)[
        "accepts"][0]["amount"] == "10000"
    signature = signed_from(challenge)
    paid = go(handler, FakeRequest(headers={
        **hint, "payment-signature": signature}))
    assert paid.status_code == 200
    gate = getattr(core, GATE_ATTR)
    assert "0xbuyer" in gate[x402_http.INTRO_SEEN_KEY]
    stored = next(iter(gate["consumed_x402"].values()))
    assert stored["pricing_schedule_version"] == "x402-intro-v1"
    assert stored["intro_price_applied"] is True
    assert stored["list_price_minor"] == 25
    second = go(handler, FakeRequest(headers=hint))
    assert decode_header(second, x402_v2.PAYMENT_REQUIRED_HEADER)[
        "accepts"][0]["amount"] == "250000"


def test_intro_status_labels_seen_payers_as_non_authoritative_seller_state(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "true")
    _, core, _ = build(tmp_path)
    gate = getattr(core, GATE_ATTR)
    gate[x402_http.INTRO_SEEN_KEY] = {
        "0xbuyer": {"pricing_schedule_version": "x402-intro-v1"}}

    status = x402_http.intro_status({"regulatory-radar": core})

    assert status["seen_payers"] == 1
    assert status["seen_payers_evidence"] == {
        "classification": "seller_reported_pricing_eligibility_state",
        "independently_verifiable": False,
        "authoritative_for_payment": False,
        "revenue_signal": False,
    }
    assert "not independent buyer or revenue proof" in status["note"]


def test_independent_evidence_index_pins_external_fixture_bytes():
    evidence = x402_http.independent_evidence_index()

    assert evidence == {
        "classification": "external_fixture_pointer_index",
        "index_posture": "seller_published_pointer_only",
        "authoritative_for_payment": False,
        "revenue_signal": False,
        "verification_required": True,
        "repository": (
            "https://github.com/smartflowproai-lang/"
            "x402-endpoint-validator"),
        "fixtures": [
            {
                "route": "regulatory-radar/scan_regulations",
                "evidence_posture": (
                    "unpaid_preflight_current_with_dated_settlement_reference"),
                "fixture_state": "matched_on_last_comparison",
                "capture_method": "unpaid_preflight",
                "captured_at": "2026-07-26T16:47:37+00:00",
                "supersedes_capture": "2026-07-24",
                "last_compared_on": "2026-07-26",
                "matched_on_last_comparison": True,
                "payment_terms_changed": False,
                "settled_flow_provenance": {
                    "current_fixture_is_settlement_receipt": False,
                    "confirmed_at_merge": (
                        "0920d50db53cbf59f20052c6c656f17f881c4b41"),
                    "pull_request": (
                        "https://github.com/smartflowproai-lang/"
                        "x402-endpoint-validator/pull/12"),
                    "payment_terms_byte_identical": True,
                },
                "pull_request": (
                    "https://github.com/smartflowproai-lang/"
                    "x402-endpoint-validator/pull/15"),
                "merge_commit": (
                    "811fef6b037cfeb71a890cac97bb822f0efcf03a"),
                "fixture_path": (
                    "tests/fixtures/viridis_regulatory_radar.json"),
                "immutable_url": (
                    "https://github.com/smartflowproai-lang/"
                    "x402-endpoint-validator/blob/"
                    "811fef6b037cfeb71a890cac97bb822f0efcf03a/"
                    "tests/fixtures/viridis_regulatory_radar.json"),
                "sha256": (
                    "f667444013029bc98e229b0d3021426d8bf18d13afe3007db419a213d0e290b5"),
            },
            {
                "route": "ghg-ledger/calculate_inventory",
                "evidence_posture": "unpaid_preflight_only",
                "fixture_state": "matched_on_last_comparison",
                "captured_on": "2026-07-26",
                "last_compared_on": "2026-07-26",
                "matched_on_last_comparison": True,
                "payment_terms_changed": False,
                "pull_request": (
                    "https://github.com/smartflowproai-lang/"
                    "x402-endpoint-validator/pull/14"),
                "merge_commit": (
                    "45b006b42a60562101a43ffc293447793900d095"),
                "fixture_path": "tests/fixtures/viridis_ghg_ledger.json",
                "immutable_url": (
                    "https://github.com/smartflowproai-lang/"
                    "x402-endpoint-validator/blob/"
                    "45b006b42a60562101a43ffc293447793900d095/"
                    "tests/fixtures/viridis_ghg_ledger.json"),
                "sha256": (
                    "8cd884c016b19c2131207365e523677a9384b8463fb45eb0ca826a89497b7d40"),
            },
        ],
    }
    evidence["fixtures"][0]["sha256"] = "forged"
    assert x402_http.independent_evidence_index()[
        "fixtures"][0]["sha256"].startswith("f6674440")


def test_wave9_intro_external_flips_first_dollar_metrics(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    monkeypatch.delenv("VIRIDIS_X402_SELF_WALLETS", raising=False)
    install_fake(monkeypatch, FakeFacilitator())
    handler, core, _ = build(tmp_path)
    hint = {"x402-payer-address": "0xStranger"}
    challenge = go(handler, FakeRequest(headers=hint))
    signature = signed_from(challenge, payer="0xStranger")
    assert go(handler, FakeRequest(headers={
        **hint, "payment-signature": signature})).status_code == 200
    metrics = x402_http.settlement_metrics({
        "regulatory-radar": getattr(core, GATE_ATTR)})["total"]
    assert metrics["external_settlements"] == 1
    assert metrics["distinct_external_payers"] == 1
    assert metrics["external_revenue_atomic"] == 10000
    assert metrics["first_external_settlement"]["tx_hash"] == "0xv2settled"


def test_wave9_allowlisted_intro_settle_stays_self(tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    monkeypatch.setenv("VIRIDIS_X402_SELF_WALLETS", "0xSelfBuyer")
    install_fake(monkeypatch, FakeFacilitator())
    handler, core, _ = build(tmp_path)
    hint = {"x402-payer-address": "0xSelfBuyer"}
    challenge = go(handler, FakeRequest(headers=hint))
    signature = signed_from(challenge, payer="0xSelfBuyer")
    assert go(handler, FakeRequest(headers={
        **hint, "payment-signature": signature})).status_code == 200
    metrics = x402_http.settlement_metrics({
        "regulatory-radar": getattr(core, GATE_ATTR)})["total"]
    assert metrics["settlements_total"] == 1
    assert metrics["self_settlements"] == 1
    assert metrics["external_settlements"] == 0
    assert metrics["first_external_settlement"] is None


def test_wave9_seen_wallet_is_full_price_across_routes(tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    radar = DummyCore()
    quantity = DummyCore()
    getattr(radar, GATE_ATTR)[x402_http.INTRO_SEEN_KEY] = {
        "0xcrossroute": {"pricing_schedule_version": "x402-intro-v1"}}
    store = StateStore(str(tmp_path / "cross-route.db"))
    handler = x402_http.make_x402_http_route(
        {"regulatory-radar": radar, "quantity-takeoff": quantity}, store,
        "https://mcp.test", tools={
            ("quantity-takeoff", "calculate_takeoff"): "calculate_takeoff"})
    args = x402_http.X402_HTTP_METADATA[
        ("quantity-takeoff", "calculate_takeoff")]["input_example"]
    challenge = go(handler, FakeRequest(
        agent="quantity-takeoff", tool="calculate_takeoff",
        headers={"x402-payer-address": "0xCrossRoute"}, body=args))
    assert decode_header(challenge, x402_v2.PAYMENT_REQUIRED_HEADER)[
        "accepts"][0]["amount"] == "500000"


def test_wave9_intro_flag_false_always_quotes_list_price(tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "0")
    handler, _, _ = build(tmp_path)
    challenge = go(handler, FakeRequest(headers={
        "x402-payer-address": "0xNeverSeen"}))
    assert decode_header(challenge, x402_v2.PAYMENT_REQUIRED_HEADER)[
        "accepts"][0]["amount"] == "250000"


def test_wave9_intro_seen_wallet_survives_restart(tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    install_fake(monkeypatch, FakeFacilitator())
    handler, _, store = build(tmp_path)
    hint = {"x402-payer-address": "0xDurable"}
    first = go(handler, FakeRequest(headers=hint))
    signature = signed_from(first, payer="0xDurable")
    assert go(handler, FakeRequest(headers={
        **hint, "payment-signature": signature})).status_code == 200
    store.close()

    second_store = StateStore(str(tmp_path / "state.db"))
    second_core = DummyCore()
    assert second_store.restore("regulatory-radar", second_core) is True
    second_core._gate_inner = second_core._run
    second_handler = x402_http.make_x402_http_route(
        {"regulatory-radar": second_core}, second_store,
        "https://mcp.test", tools=TEST_TOOLS)
    challenge = go(second_handler, FakeRequest(headers=hint))
    assert decode_header(challenge, x402_v2.PAYMENT_REQUIRED_HEADER)[
        "accepts"][0]["amount"] == "250000"


def test_wave9_seen_hint_spoof_cannot_get_second_intro(tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    install_fake(monkeypatch, FakeFacilitator())
    handler, core, _ = build(tmp_path)
    getattr(core, GATE_ATTR)[x402_http.INTRO_SEEN_KEY] = {
        "0xbuyer": {"pricing_schedule_version": "x402-intro-v1"}}
    spoof_hint = {"x402-payer-address": "0xFreshSpoof"}
    intro_challenge = go(handler, FakeRequest(headers=spoof_hint))
    signature = signed_from(intro_challenge, payer="0xBuyer")
    refused = go(handler, FakeRequest(headers={
        **spoof_hint, "payment-signature": signature}))
    assert refused.status_code == 402
    assert "already used" in body_of(refused)["error"]
    full = decode_header(refused, x402_v2.PAYMENT_REQUIRED_HEADER)
    assert full["accepts"][0]["amount"] == "250000"
    assert core.calls == []


def test_bazaar_examples_validate_for_every_route_and_method(monkeypatch):
    arm(monkeypatch)
    for key, meta in x402_http.X402_HTTP_METADATA.items():
        for method in ("GET", "POST"):
            extension = x402_v2.build_bazaar_extension(
                method, meta["input_schema"], meta["input_example"],
                meta["output_example"])
            assert x402_v2._matches_schema(
                extension["info"], extension["schema"]), key
            assert extension["info"]["input"]["method"] == method


@pytest.mark.parametrize("agent,tool,minor,atomic", [
    ("quantity-takeoff", "calculate_takeoff", 50, "500000"),
    ("disclosure-compiler", "compile_disclosure", 200, "2000000"),
])
def test_wave8_routes_have_schema_valid_shape_and_exact_amount(
        monkeypatch, agent, tool, minor, atomic):
    arm(monkeypatch)
    meta = x402_http.X402_HTTP_METADATA[(agent, tool)]
    required = x402_v2.build_payment_required(
        agent, tool, minor, f"https://mcp.test/x402/{agent}/{tool}",
        "POST", meta)
    assert required["accepts"][0]["amount"] == atomic
    bazaar = required["extensions"]["bazaar"]
    assert x402_v2._matches_schema(bazaar["info"], bazaar["schema"])
    assert "pairs with" in meta["description"].lower()


@pytest.mark.parametrize("agent,tool", [
    ("quantity-takeoff", "calculate_takeoff"),
    ("disclosure-compiler", "compile_disclosure"),
])
def test_wave8_routes_settle_before_serve_and_replay_once(
        tmp_path, monkeypatch, agent, tool):
    arm(monkeypatch)
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    handler, core, _ = build(tmp_path, agent=agent, tool=tool)
    args = x402_http.X402_HTTP_METADATA[(agent, tool)]["input_example"]
    challenge = go(handler, FakeRequest(agent=agent, tool=tool, body=args))
    signature = signed_from(challenge)
    request = FakeRequest(agent=agent, tool=tool, body=args,
                          headers={"payment-signature": signature})
    paid = go(handler, request)
    assert paid.status_code == 200
    assert len(core.calls) == 1
    assert core.calls[0]["action"] == x402_http.X402_HTTP_TOOLS[(agent, tool)]
    replay = go(handler, request)
    assert replay.status_code == 402
    assert body_of(replay)["idempotent"] is True
    assert len(core.calls) == 1


@pytest.mark.parametrize("agent,tool", [
    ("quantity-takeoff", "calculate_takeoff"),
    ("disclosure-compiler", "compile_disclosure"),
])
def test_wave8_routes_never_execute_on_settlement_error(
        tmp_path, monkeypatch, agent, tool):
    arm(monkeypatch)
    install_fake(monkeypatch, FakeFacilitator(settle=False))
    handler, core, _ = build(tmp_path, agent=agent, tool=tool)
    args = x402_http.X402_HTTP_METADATA[(agent, tool)]["input_example"]
    challenge = go(handler, FakeRequest(agent=agent, tool=tool, body=args))
    signature = signed_from(challenge)
    refused = go(handler, FakeRequest(
        agent=agent, tool=tool, body=args,
        headers={"payment-signature": signature}))
    assert refused.status_code == 402
    assert core.calls == []


# X2-3: the real transport obtains a fresh route-bound JWT every call.
def test_X2_3_fresh_request_bound_jwt_per_facilitator_call(monkeypatch):
    tokens = []

    def fake_jwt(key_id, secret, method, host, path):
        token = f"jwt-{len(tokens) + 1}-{path}"
        tokens.append((token, method, host, path))
        return token

    requests = []

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok":true}'

    def fake_open(request, timeout):
        requests.append(request)
        return Response()

    monkeypatch.setattr(x402_rail, "cdp_jwt", fake_jwt)
    monkeypatch.setattr(x402_v2.urllib.request, "urlopen", fake_open)
    cfg = {"cdp_key_id": "id", "cdp_key_secret": "secret",
           "timeout_s": 1}
    x402_v2._facilitator_post("https://fac.test/verify", {}, cfg)
    x402_v2._facilitator_post("https://fac.test/settle", {}, cfg)
    assert [entry[3] for entry in tokens] == ["/verify", "/settle"]
    assert requests[0].get_header("Authorization") == "Bearer jwt-1-/verify"
    assert requests[1].get_header("Authorization") == "Bearer jwt-2-/settle"


# X2-4/X2-5: settle, persist, then serve once; replay is idempotent refusal.
def test_X2_4_X2_5_settle_persist_serve_and_replay_refusal(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    handler, core, _ = build(tmp_path)
    challenge = go(handler, FakeRequest())
    signature = signed_from(challenge)
    paid = go(handler, FakeRequest(headers={
        "payment-signature": signature}))
    assert paid.status_code == 200
    assert [phase for phase, _ in fake.calls] == ["verify", "settle"]
    assert len(core.calls) == 1
    stored = next(iter(getattr(core, GATE_ATTR)["consumed_x402"].values()))
    assert stored["tx_hash"] == "0xv2settled"
    assert stored["payment_identifier"].startswith("nonce:")
    replay = go(handler, FakeRequest(headers={
        "payment-signature": signature}))
    assert replay.status_code == 402
    assert body_of(replay)["idempotent"] is True
    assert body_of(replay)["transaction"] == "0xv2settled"
    assert len(fake.calls) == 2 and len(core.calls) == 1


def test_wave8_self_settlement_is_classified_and_persisted(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("VIRIDIS_X402_SELF_WALLETS", "0xOther, 0xbuyer")
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    handler, core, store = build(tmp_path)
    signature = signed_from(go(handler, FakeRequest()))
    assert go(handler, FakeRequest(headers={
        "payment-signature": signature})).status_code == 200
    stored = next(iter(getattr(core, GATE_ATTR)["consumed_x402"].values()))
    assert stored["payer_wallet"] == "0xBuyer"
    assert stored["route"] == "regulatory-radar/scan_regulations"
    assert stored["self_settle"] is True
    assert stored["classification_version"] == 1
    assert stored["amount_atomic"] == "250000"
    assert stored["timestamp"].endswith("+00:00")
    store.close()

    restored_store = StateStore(str(tmp_path / "state.db"))
    restored = DummyCore()
    assert restored_store.restore("regulatory-radar", restored) is True
    metrics = x402_http.settlement_metrics({
        "regulatory-radar": getattr(restored, GATE_ATTR)})
    assert metrics["total"] == {
        "settlements_total": 1, "self_settlements": 1,
        "external_settlements": 0, "distinct_external_payers": 0,
        "repeat_external_purchases": 0,
        "external_revenue_atomic": 0, "first_external_settlement": None}


def test_wave8_external_distinct_payers_first_flip_and_empty_allowlist():
    first = {
        "surface": "http-402-v2", "classification_version": 1,
        "route": "quantity-takeoff/calculate_takeoff",
        "payer_wallet": "0xExternalA", "self_settle": False,
        "amount_atomic": "500000", "tx_hash": "0xfirst",
        "timestamp": "2026-07-20T01:00:00+00:00"}
    second = {**first, "payer_wallet": "0xExternalB",
              "tx_hash": "0xsecond", "amount_atomic": "700000",
              "timestamp": "2026-07-20T02:00:00+00:00"}
    repeat = {**second, "tx_hash": "0xthird"}
    legacy_seed = {"surface": "http-402-v2", "tx_hash": "0xlegacy",
                   "amount_atomic": "99999999"}
    metrics = x402_http.settlement_metrics({"quantity-takeoff": {
        "consumed_x402": {"a": second, "b": first, "c": repeat,
                           "legacy": legacy_seed}}})
    total = metrics["total"]
    assert total["settlements_total"] == 3
    assert total["self_settlements"] == 0
    assert total["external_settlements"] == 3
    assert total["distinct_external_payers"] == 2
    assert total["repeat_external_purchases"] == 1
    assert total["external_revenue_atomic"] == 1900000
    assert total["first_external_settlement"] == {
        "tx_hash": "0xfirst", "timestamp": "2026-07-20T01:00:00+00:00"}
    assert metrics["per_route"][
        "disclosure-compiler/compile_disclosure"][
            "first_external_settlement"] is None
    assert metrics["per_route"][
        "quantity-takeoff/calculate_takeoff"][
            "repeat_external_purchases"] == 1


def test_paid_success_offers_next_paid_routes_without_auto_execution(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    install_fake(monkeypatch, FakeFacilitator())
    handler, core, _ = build(tmp_path)
    challenge = go(handler, FakeRequest())
    paid = go(handler, FakeRequest(headers={
        "payment-signature": signed_from(challenge)}))
    assert paid.status_code == 200
    commerce = body_of(paid)["viridis_commerce"]
    assert commerce["current_route"] == \
        "regulatory-radar/scan_regulations"
    assert commerce["auto_execute"] is False
    assert commerce["payment_required"] is True
    assert commerce["buyer_authorization_required"] is True
    repeat = commerce["repeat_purchase"]
    assert f"{repeat['agent']}/{repeat['tool']}" == (
        "regulatory-radar/scan_regulations")
    assert repeat["endpoint"] == (
        "https://mcp.test/x402/regulatory-radar/scan_regulations")
    assert repeat["mcp_endpoint"] == (
        "https://mcp.test/regulatory-radar/mcp")
    assert repeat["method"] == "POST"
    assert repeat["price_minor"] == 25
    assert repeat["amount_atomic_usdc"] == "250000"
    assert repeat["input_schema"]["type"] == "object"
    assert repeat["input_example"]
    assert repeat["required_buyer_inputs"] == list(
        repeat["input_schema"].get("required", []))
    assert "new caller-owned request" in repeat["input_policy"]
    assert repeat["quote"]["preflight_required"] is True
    assert repeat["quote"]["authoritative_source"] == (
        "repeat_route_unpaid_http_402")
    assert repeat["quote"]["payer_hint_value_source"] == (
        "caller_public_signing_address")
    assert repeat["quote"]["payer_hint_required_for_exact_quote"] is True
    assert repeat["quote"]["payer_hint_authorizes_payment"] is False
    assert repeat["quote"]["advertised_price_posture"] == (
        "returning_payer_list_price")
    assert {f"{offer['agent']}/{offer['tool']}"
            for offer in commerce["next_paid_routes"]} == {
                "disclosure-compiler/compile_disclosure",
                "taxcredit-engine/calculate_tax_credit",
            }
    assert all(offer["method"] == "POST"
               for offer in commerce["next_paid_routes"])
    for offer in commerce["next_paid_routes"]:
        assert offer["input_schema"]["type"] == "object"
        assert offer["input_example"]
        assert offer["description"]
        assert offer["mcp_endpoint"] == (
            f"https://mcp.test/{offer['agent']}/mcp")
        assert offer["required_buyer_inputs"] == list(
            offer["input_schema"].get("required", []))
        assert offer["quote"]["preflight_required"] is True
        assert offer["quote"]["authoritative_source"] == (
            "next_route_unpaid_http_402")
        assert offer["quote"]["payer_hint_value_source"] == (
            "caller_public_signing_address")
        assert offer["quote"]["payer_hint_required_for_exact_quote"] is True
        assert offer["quote"]["payer_hint_authorizes_payment"] is False
        assert offer["quote"]["advertised_price_posture"] == (
            "returning_payer_list_price")
    assert len(core.calls) == 1


def test_repeat_purchase_contract_is_available_for_fixed_price_hive(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    install_fake(monkeypatch, FakeFacilitator())
    handler, core, _ = build(
        tmp_path, agent="hive", tool="solve")
    challenge = go(handler, FakeRequest(body={
        "problem": "Compare two deployment options.",
        "budget_minor": 500,
        "depth": 0,
        "redundancy": 1,
        "fee_bps": 0,
    }, agent="hive", tool="solve"))
    paid = go(handler, FakeRequest(
        headers={"payment-signature": signed_from(challenge)},
        body={
            "problem": "Compare two deployment options.",
            "budget_minor": 500,
            "depth": 0,
            "redundancy": 1,
            "fee_bps": 0,
        },
        agent="hive", tool="solve"))
    assert paid.status_code == 200
    repeat = body_of(paid)["viridis_commerce"]["repeat_purchase"]
    assert repeat["agent"] == "hive"
    assert repeat["price_minor"] == 500
    assert repeat["amount_atomic_usdc"] == "5000000"
    assert repeat["quote"]["authoritative_source"] == (
        "repeat_route_unpaid_http_402")
    assert repeat["quote"]["payer_hint_required_for_exact_quote"] is False
    assert repeat["quote"]["payer_hint_authorizes_payment"] is False
    assert core.calls == [{
        "action": "solve",
        "problem": "Compare two deployment options.",
        "budget_minor": 500,
        "depth": 0,
        "redundancy": 1,
        "fee_bps": 0,
    }]


def test_wave8_empty_allowlist_is_fail_safe_external(monkeypatch):
    monkeypatch.delenv("VIRIDIS_X402_SELF_WALLETS", raising=False)
    result = {"tx_hash": "0xstranger", "network": "eip155:8453",
              "amount_atomic": "2000000"}
    record = x402_http._classified_settlement(
        {"payload": {"authorization": {"from": "0xAnyBuyer"}}},
        "disclosure-compiler", "compile_disclosure", result, "nonce:n")
    assert record["self_settle"] is False


def test_X2_5_replay_refusal_survives_store_restart(tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    handler, _, store = build(tmp_path)
    challenge = go(handler, FakeRequest())
    signature = signed_from(challenge, nonce="0x" + "cd" * 32)
    assert go(handler, FakeRequest(headers={
        "payment-signature": signature})).status_code == 200
    store.close()

    second_store = StateStore(str(tmp_path / "state.db"))
    second_core = DummyCore()
    assert second_store.restore("regulatory-radar", second_core) is True
    second_core._gate_inner = second_core._run
    calls_before_replay = list(second_core.calls)
    second = x402_http.make_x402_http_route(
        {"regulatory-radar": second_core}, second_store,
        "https://mcp.test", tools=TEST_TOOLS)
    replay = go(second, FakeRequest(headers={
        "payment-signature": signature}))
    assert replay.status_code == 402 and body_of(replay)["idempotent"] is True
    assert len(fake.calls) == 2 and second_core.calls == calls_before_replay


# X2-6: every facilitator/extension/persistence error path serves nothing.
@pytest.mark.parametrize("fake", [
    FakeFacilitator(verify=False),
    FakeFacilitator(settle=False),
    FakeFacilitator(fail="verify"),
    FakeFacilitator(fail="settle"),
])
def test_X2_6_facilitator_errors_never_execute(tmp_path, monkeypatch, fake):
    arm(monkeypatch)
    install_fake(monkeypatch, fake)
    handler, core, _ = build(tmp_path)
    signature = signed_from(go(handler, FakeRequest()))
    response = go(handler, FakeRequest(headers={
        "payment-signature": signature}))
    assert response.status_code == 402
    assert core.calls == []


def test_X2_6_verify_extension_rejection_never_settles_or_executes(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = FakeFacilitator(verify_status="rejected")
    install_fake(monkeypatch, fake)
    handler, core, _ = build(tmp_path)
    signature = signed_from(go(handler, FakeRequest()))
    response = go(handler, FakeRequest(headers={
        "payment-signature": signature}))
    assert response.status_code == 402
    assert [phase for phase, _ in fake.calls] == ["verify"]
    assert core.calls == []


def test_X2_6_settle_extension_rejection_records_payment_but_serves_nothing(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = FakeFacilitator(settle_status="rejected")
    install_fake(monkeypatch, fake)
    handler, core, _ = build(tmp_path)
    signature = signed_from(go(handler, FakeRequest()))
    response = go(handler, FakeRequest(headers={
        "payment-signature": signature}))
    assert response.status_code == 502
    assert core.calls == []
    stored = getattr(core, GATE_ATTR)["consumed_x402"]
    assert len(stored) == 1
    assert next(iter(stored.values()))["tx_hash"] == "0xv2settled"


def test_X2_6_persistence_failure_after_settle_serves_nothing(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    handler, core, store = build(tmp_path)
    monkeypatch.setattr(store, "save", lambda *args: False)
    signature = signed_from(go(handler, FakeRequest()))
    response = go(handler, FakeRequest(headers={
        "payment-signature": signature}))
    assert response.status_code == 500
    assert "persistence failed" in body_of(response)["error"]
    assert core.calls == []
    assert getattr(core, GATE_ATTR)["consumed_x402"] == {}


def test_wave9_intro_persistence_failure_reverts_seen_payer(
        tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_INTRO_ENABLED", "1")
    install_fake(monkeypatch, FakeFacilitator())
    handler, core, store = build(tmp_path)
    monkeypatch.setattr(store, "save", lambda *args: False)
    hint = {"x402-payer-address": "0xRollback"}
    challenge = go(handler, FakeRequest(headers=hint))
    signature = signed_from(challenge, payer="0xRollback")
    response = go(handler, FakeRequest(headers={
        **hint, "payment-signature": signature}))
    assert response.status_code == 500
    gate = getattr(core, GATE_ATTR)
    assert gate["consumed_x402"] == {}
    assert gate[x402_http.INTRO_SEEN_KEY] == {}


# X2-7: master off and incomplete explicitly-requested v2 both refuse.
def test_X2_7_master_kill_switch_is_503(tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_ENABLED", "0")
    handler, core, _ = build(tmp_path)
    response = go(handler, FakeRequest())
    assert response.status_code == 503 and core.calls == []


def test_X2_7_v2_flag_on_with_incomplete_config_is_503(tmp_path, monkeypatch):
    arm(monkeypatch)
    monkeypatch.setenv("X402_V2_PAY_TO", "")
    handler, core, _ = build(tmp_path)
    response = go(handler, FakeRequest())
    assert response.status_code == 503 and core.calls == []


def test_health_inventory_surfaces_bazaar_feedback(tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = FakeFacilitator(verify_status="accepted",
                           settle_status="processing")
    install_fake(monkeypatch, fake)
    handler, _, _ = build(tmp_path)
    signature = signed_from(go(handler, FakeRequest()))
    assert go(handler, FakeRequest(headers={
        "payment-signature": signature})).status_code == 200
    entries = {item["agent"]: item for item in
               x402_http.discovery_entries("https://mcp.test")}
    status = entries["regulatory-radar"]["bazaar_extension_responses"]
    assert entries["regulatory-radar"]["x402_version"] == 2
    assert status["verify"]["status"] == "accepted"
    assert status["settle"]["status"] == "processing"
