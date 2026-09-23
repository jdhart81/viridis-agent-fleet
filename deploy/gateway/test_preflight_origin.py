"""A domain alias must not weaken payment binding or change other services."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import preflight_origin
import preflight_watch
from test_preflight_watch import core, inputs
from test_x402_v2 import (arm, build, go, FakeRequest, decode_header,
                         signed_from, install_fake, FakeFacilitator)

SECURITY = preflight_origin.SECURITY_BASE
MARKER = {preflight_origin.ORIGIN_HEADER: SECURITY}
PAID_PATH = "/x402/security-preflight/security_preflight"


@pytest.mark.parametrize("headers,expected", [
    ({}, "https://mcp.test"),
    (MARKER, SECURITY),
    ({"host": "attacker.example", "x-forwarded-host": "attacker.example"}, "https://mcp.test"),
    ({preflight_origin.ORIGIN_HEADER: "https://attacker.example"}, "https://mcp.test"),
])
def test_quotes_bind_only_supported_origin(tmp_path, monkeypatch, headers, expected):
    arm(monkeypatch)
    handler, backend, store = build(tmp_path, agent="security-preflight", tool="security_preflight")
    response = go(handler, FakeRequest(headers=headers, body=inputs(),
        agent="security-preflight", tool="security_preflight"))
    assert response.status_code == 402
    terms = decode_header(response, "payment-required")
    assert terms["resource"]["url"] == expected + PAID_PATH
    assert backend.calls == []


def test_domain_marker_does_not_move_other_services(tmp_path, monkeypatch):
    arm(monkeypatch)
    handler, backend, store = build(tmp_path)
    response = go(handler, FakeRequest(headers=MARKER))
    assert response.status_code == 402
    assert decode_header(response, "payment-required")["resource"]["url"].startswith("https://mcp.test/")
    assert backend.calls == []


def test_maxwell_security_quote_and_cross_origin_payment_refusal(tmp_path, monkeypatch):
    import x402_http
    arm(monkeypatch)
    route = ("maxwell-defense", "rehearse_defense")
    monkeypatch.setitem(x402_http.X402_HTTP_TOOLS, route, "rehearse_defense")
    handler, backend, store = build(tmp_path, agent=route[0], tool=route[1])
    args = x402_http.X402_HTTP_METADATA[route]["input_example"]
    def request(headers):
        return FakeRequest(headers=headers, body=args, agent=route[0], tool=route[1])
    quoted = go(handler, request(MARKER))
    assert quoted.status_code == 402
    terms = decode_header(quoted, "payment-required")
    assert terms["resource"]["url"] == SECURITY + "/x402/maxwell-defense/rehearse_defense"
    assert terms["accepts"][0]["amount"] == "1000000"
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    wrong = go(handler, request({"payment-signature": signed_from(quoted)}))
    assert wrong.status_code == 402 and "resource_mismatch" in wrong.body.decode()
    assert fake.calls == [] and backend.calls == []


def test_signed_retry_cannot_cross_origins(tmp_path, monkeypatch):
    arm(monkeypatch)
    fake = FakeFacilitator()
    install_fake(monkeypatch, fake)
    handler, backend, store = build(tmp_path, agent="security-preflight", tool="security_preflight")
    def request(headers):
        return FakeRequest(headers=headers, body=inputs(), agent="security-preflight", tool="security_preflight")
    challenge = go(handler, request(MARKER))
    signed = signed_from(challenge)
    wrong_origin = go(handler, request({"payment-signature": signed}))
    assert wrong_origin.status_code == 402
    assert "resource_mismatch" in wrong_origin.body.decode()
    assert fake.calls == [] and backend.calls == []
    paid = go(handler, request({**MARKER, "payment-signature": signed}))
    assert paid.status_code == 200
    assert len(backend.calls) == 1
    assert json.loads(paid.body)["viridis_commerce"]["change_check"]["endpoint"].startswith(SECURITY)
    assert json.loads(paid.body)["viridis_commerce"]["next_paid_routes"][0]["endpoint"].startswith("https://mcp.test/")


def test_change_check_quotes_security_origin_without_creating_state(core):
    app = Starlette(routes=[Route("/watch", preflight_watch.make_watch_route(
        {"security-preflight": core}, "https://mcp.test"), methods=["POST"])])
    with TestClient(app) as client:
        response = client.post("/watch", json={"inputs": inputs()}, headers=MARKER)
    assert response.status_code == 200
    result = response.json()
    assert result["quote_request"]["url"] == SECURITY + PAID_PATH
    assert result["payment_authorized"] is False
    assert core._stored_receipt_count() == 0
