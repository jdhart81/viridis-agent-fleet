import base64
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from viridis_market_router import (MarketRouter, RouterError, SellerResource,
                                   SpendMandate, X402Buyer, load_catalog)


RESOURCE = SellerResource(
    id="outside-carbon-api", url="https://seller.example/x402/carbon",
    description="auditable embodied carbon calculator",
    amount_atomic=500_000, network="eip155:8453", pay_to="0xSeller",
    trust_score=0.9, latency_ms=200, source="test")


def mandate(**updates):
    values = dict(
        purpose="buy an auditable carbon calculation",
        max_total_atomic=1_000_000, max_per_call_atomic=600_000,
        allowed_networks=["eip155:8453"], allowed_payees=["0xSeller"],
        allowed_resource_prefixes=["https://seller.example/x402/"],
        expires_at_epoch=2_000_000_000, max_latency_ms=1000,
        min_trust_score=0.8)
    values.update(updates)
    return SpendMandate.create(**values)


def b64(value):
    return base64.b64encode(json.dumps(value).encode()).decode()


class Response:
    def __init__(self, status, payload, headers=None):
        self.status = status
        self.payload = payload
        self.headers = headers or {}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit): return json.dumps(self.payload).encode()


def required():
    return {"x402Version": 2,
            "resource": {"url": RESOURCE.url, "description": RESOURCE.description},
            "accepts": [{"scheme": "exact", "network": RESOURCE.network,
                         "asset": "0xUSDC", "amount": "500000",
                         "payTo": RESOURCE.pay_to}]}


def test_router_ranks_relevance_then_enforces_budget_and_trust():
    other = SellerResource(
        id="weather", url="https://seller.example/x402/weather",
        description="temperature forecast", amount_atomic=100,
        network="eip155:8453", pay_to="0xSeller", trust_score=0.9,
        latency_ms=100)
    rows = MarketRouter([other, RESOURCE]).rank(
        "auditable carbon calculator", mandate(), now_epoch=1_900_000_000)
    assert rows[0]["resource"] == RESOURCE and rows[0]["eligible"]
    too_small = mandate(max_per_call_atomic=100)
    rows = MarketRouter([RESOURCE]).rank(
        "carbon", too_small, now_epoch=1_900_000_000)
    assert not rows[0]["eligible"]
    assert rows[0]["refusal_reason"] == "per_call_cap_exceeded"


def test_private_urls_and_changed_seller_resource_are_refused():
    with pytest.raises(RouterError, match="private-network"):
        SellerResource.from_x402({
            "resource": {"url": "https://127.0.0.1/tool"},
            "accepts": [{"amount": "1"}]})

    changed = required()
    changed["resource"]["url"] = "https://other.example/tool"
    error = urllib.error.HTTPError(
        RESOURCE.url, 402, "payment", {"PAYMENT-REQUIRED": b64(changed)}, None)
    buyer = X402Buyer(mandate(), opener=lambda *args, **kwargs: (_ for _ in ()).throw(error))
    with pytest.raises(RouterError, match="changed"):
        buyer.quote(RESOURCE, {})


def test_no_signer_means_no_paid_request():
    calls = []
    error = urllib.error.HTTPError(
        RESOURCE.url, 402, "payment", {"PAYMENT-REQUIRED": b64(required())}, None)
    def opener(request, timeout):
        calls.append(request)
        raise error
    buyer = X402Buyer(mandate(max_total_atomic=900_000), opener=opener)
    with pytest.raises(RouterError, match="signer_required"):
        buyer.execute(RESOURCE, {"input": 1}, signer=None)
    assert len(calls) == 1 and "Payment-signature" not in calls[0].headers
    assert buyer.spent_atomic == 0


def test_injected_signer_completes_once_and_receipt_increments_cap():
    calls = []
    quote_error = urllib.error.HTTPError(
        RESOURCE.url, 402, "payment", {"PAYMENT-REQUIRED": b64(required())}, None)
    def opener(request, timeout):
        calls.append(request)
        if len(calls) in (1, 3):
            raise quote_error
        return Response(200, {"status": "ok"}, {
            "PAYMENT-RESPONSE": b64({"success": True,
                                     "transaction": "0xexternal"})})
    signed = []
    def signer(payment_required, spend_mandate):
        signed.append((payment_required, spend_mandate))
        return "caller-owned-signed-payload"
    buyer = X402Buyer(mandate(max_total_atomic=900_000), opener=opener)
    result = buyer.execute(RESOURCE, {"input": 1}, signer=signer)
    assert result["receipt"]["transaction"] == "0xexternal"
    assert result["spent_atomic"] == 500_000 and len(signed) == 1
    assert calls[1].headers["Payment-signature"] == \
        "caller-owned-signed-payload"
    with pytest.raises(RouterError, match="total_cap_exceeded"):
        buyer.execute(RESOURCE, {"input": 2}, signer=signer)
    assert len(calls) == 3  # second attempt stops after its unpaid quote


def test_catalog_loader_is_bounded_and_normalizes_x402_resources():
    payload = {"resources": [{
        "id": RESOURCE.id,
        "resource": {"url": RESOURCE.url,
                     "description": RESOURCE.description},
        "accepts": [{"amount": "500000", "network": "eip155:8453",
                     "payTo": "0xSeller"}],
        "trustScore": 0.9, "latencyMs": 200,
    }]}
    values = load_catalog(
        "https://catalog.example/resources",
        opener=lambda request, timeout: Response(200, payload))
    assert len(values) == 1
    assert values[0].id == RESOURCE.id
    assert values[0].url == RESOURCE.url
    assert values[0].amount_atomic == RESOURCE.amount_atomic
    assert values[0].source == "https://catalog.example/resources"


def test_mandate_json_contains_no_wallet_or_private_key_field():
    encoded = json.dumps(mandate().to_dict(), sort_keys=True).lower()
    assert "private" not in encoded and "seed" not in encoded
    assert "wallet" not in encoded and "sign" not in encoded
