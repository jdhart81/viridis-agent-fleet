import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import viridis_preflight_watch as client


def paid_result():
    value = {"status": "ok", "receipt": {"receipt_id": "vsr_" + "a" * 24}}
    delivery = {"version": "viridis-paid-delivery-v1",
                "route": "security-preflight/security_preflight",
                "settlement": {"transaction": "local-test-reference"},
                "result_sha256": client._digest(value)}
    delivery["receipt_sha256"] = client._digest(delivery)
    return {**value, "viridis_delivery": delivery}


def test_saved_result_integrity_checked_before_reading_baseline():
    value = paid_result()
    assert client.baseline_from_paid_result(value) == "vsr_" + "a" * 24
    for section in ["receipt", "viridis_delivery"]:
        damaged = copy.deepcopy(value)
        damaged[section]["changed"] = True
        with pytest.raises(ValueError, match="digest mismatch"):
            client.baseline_from_paid_result(damaged)


def test_client_uses_only_free_change_endpoint(monkeypatch):
    calls = []
    def post(url, payload, timeout):
        calls.append((url, payload))
        return {"status_code": 200, "body": {
            "version": "viridis-preflight-watch-v1", "decision": "UNCHANGED",
            "payment_authorized": False, "tool_executed": False}}
    monkeypatch.setattr(client, "_post", post)
    assert client.check("https://mcp.test", {"manifest": {}}, "vsr_" + "a" * 24)["decision"] == "UNCHANGED"
    assert calls == [("https://mcp.test/security-preflight/watch", {
        "inputs": {"manifest": {}}, "baseline_receipt_id": "vsr_" + "a" * 24})]


@pytest.mark.parametrize("base", ["http://unsafe.example", "https://user:secret@example.com",
                                  "https://example.com?secret=bad"])
def test_client_rejects_unsafe_transport(base):
    with pytest.raises(ValueError, match="HTTPS"):
        client.check(base, {})
