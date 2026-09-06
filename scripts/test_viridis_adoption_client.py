import io
import json
import urllib.error

import pytest

from scripts import viridis_adoption_client as client


class Response:
    def __init__(self, status, payload, headers=None):
        self.status = status
        self._payload = payload
        self.headers = headers or {}

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def ready_plan():
    return {
        "decision": "READY_FOR_QUOTE",
        "integration": {
            "route": "regulatory-radar/monitor_changes",
            "quote_request": {
                "url": "https://mcp.test/x402/regulatory-radar/monitor_changes",
                "body": {"jurisdiction": "US", "lookback_days": 90},
            },
        },
    }


def test_build_plan_posts_only_the_buyer_owned_inputs(monkeypatch):
    seen = []

    def open_(request, timeout):
        seen.append((request, timeout))
        return Response(200, ready_plan())

    monkeypatch.setattr(client.urllib.request, "urlopen", open_)
    result = client.build_plan(
        "https://mcp.test",
        "Monitor regulatory changes",
        {"jurisdiction": "US", "lookback_days": 90},
        25,
        5,
    )
    assert result["decision"] == "READY_FOR_QUOTE"
    payload = json.loads(seen[0][0].data.decode("utf-8"))
    assert payload == {
        "objective": "Monitor regulatory changes",
        "inputs": {"jurisdiction": "US", "lookback_days": 90},
        "max_price_minor": 25,
    }
    assert seen[0][0].full_url == "https://mcp.test/adopt"


def test_fetch_quote_requires_402_and_never_creates_payment(monkeypatch):
    def open_(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            402,
            "Payment Required",
            {"PAYMENT-REQUIRED": "encoded-contract"},
            io.BytesIO(b'{"error":"PAYMENT-SIGNATURE required"}'),
        )

    monkeypatch.setattr(client.urllib.request, "urlopen", open_)
    quote = client.fetch_unpaid_quote(ready_plan(), 5)
    assert quote["status"] == "UNPAID_QUOTE_READY"
    assert quote["payment_required"] == "encoded-contract"
    assert quote["payment_attempted"] is False
    assert quote["wallet_loaded"] is False
    assert quote["signature_created"] is False


def test_non_ready_plan_and_non_402_response_fail_closed(monkeypatch):
    with pytest.raises(ValueError, match="not READY_FOR_QUOTE"):
        client.fetch_unpaid_quote({"decision": "NEEDS_INPUT"}, 5)

    monkeypatch.setattr(
        client.urllib.request,
        "urlopen",
        lambda request, timeout: Response(200, {"status": "unexpected"}),
    )
    with pytest.raises(RuntimeError, match="expected an unpaid HTTP 402"):
        client.fetch_unpaid_quote(ready_plan(), 5)
