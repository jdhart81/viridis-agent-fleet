import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import meshmcp_stage_a_probe as probe


def payment_required(**updates):
    accepted = {
        "amount": "10000",
        "asset": probe.EXPECTED["asset"],
        "network": probe.EXPECTED["network"],
        "payTo": probe.EXPECTED["pay_to"],
        "scheme": probe.EXPECTED["scheme"],
    }
    accepted.update(updates.pop("accepted", {}))
    required = {
        "accepts": [accepted],
        "error": "PAYMENT-SIGNATURE required",
        "resource": {"url": probe.ENDPOINT},
        "x402Version": 2,
    }
    required.update(updates)
    return base64.b64encode(
        json.dumps(required, separators=(",", ":")).encode()).decode()


def response(header=None, body=None, status=402):
    return (
        status,
        {"PAYMENT-REQUIRED": header or payment_required()},
        json.dumps(
            body or {"error": "PAYMENT-SIGNATURE required"}).encode(),
    )


def test_probe_emits_exact_unsigned_correlation_contract():
    result = probe.probe(lambda: response())
    assert result == {
        "status": "verified_unpaid",
        "tool": "regulatory-radar.scan_regulations",
        "request_sha256": probe.REQUEST_SHA256,
        **probe.EXPECTED,
        "payment_state": "required_unpaid",
        "mesh_peer_id": "must_be_filled_from_mesh_transport_proof",
        "payer_address": "omitted",
        "private_key": "never_present",
    }


@pytest.mark.parametrize(("reply", "message"), [
    (lambda: response(status=200), "expected HTTP 402"),
    (lambda: response(header="not-base64"), "valid base64 JSON"),
    (lambda: response(header=payment_required(
        accepted={"amount": "10001"})), "contract drifted"),
    (lambda: response(body={"error": "different"}), "contract drifted"),
])
def test_probe_fails_closed_on_non_402_or_contract_drift(reply, message):
    with pytest.raises(probe.StageAError, match=message):
        probe.probe(reply)


def test_probe_request_hash_pins_exact_ordered_payload():
    assert probe.REQUEST_BYTES == (
        b'{"jurisdiction":"US","sector":"energy",'
        b'"query":"45V clean energy tax credit emissions disclosure"}')
    assert len(probe.REQUEST_SHA256) == 64
