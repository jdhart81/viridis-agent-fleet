import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import commercial_outcome_exporter as exporter
import commercial_outcome_outbox as outbox
from fleet_settlement_overlay import bind_security_preflight_delivery


def private_key_b64():
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(raw).decode("ascii")


def settlement():
    return {
        "route": "security-preflight/security_preflight",
        "surface": "http-402-v2",
        "classification_version": 1,
        "self_settle": False,
        "currency": "USDC",
        "currency_decimals": 6,
        "asset": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "network": "eip155:8453",
        "timestamp": "2026-08-04T15:00:00+00:00",
        "payment_identifier": "nonce:buyer-order-1",
        "tx_hash": "0xexternal-settlement",
        "payer_wallet": "0xexternal-buyer",
        "amount_atomic": "1000000",
        "delivery_status": "delivered",
        "delivery_recorded_at": "2026-08-04T15:00:01+00:00",
        "result_artifact_sha256": "a" * 64,
        "delivery_evidence_sha256": "b" * 64,
        "result_receipt_id": "vsr_example",
        "settlement_receipt": {"success": True},
    }


def test_export_is_signed_private_and_operator_review_only():
    packet = exporter.build_commercial_export(
        settlement(),
        private_key_pkcs8_b64=private_key_b64(),
        key_id="fleet-commercial-v1",
    )
    assert packet["status"] == "PENDING_OPERATOR_REVIEW"
    assert packet["automaticPostAllowed"] is False
    receipt = packet["commercialImport"]["receipt"]
    assert receipt["payment"]["status"] == "verified"
    assert receipt["delivery"]["status"] == "delivered"
    assert receipt["usefulness"]["status"] == "unknown"
    assert receipt["repeatPurchase"]["status"] == "unknown"
    serialized = json.dumps(packet).lower()
    assert "0xexternal-buyer" not in serialized
    assert "0xexternal-settlement" not in serialized


def test_outbox_is_idempotent_and_owner_only(tmp_path):
    key = private_key_b64()
    first = outbox.write_pending_export(
        settlement(),
        private_key_pkcs8_b64=key,
        key_id="fleet-commercial-v1",
        outbox_dir=str(tmp_path / "pending"),
    )
    second = outbox.write_pending_export(
        settlement(),
        private_key_pkcs8_b64=key,
        key_id="fleet-commercial-v1",
        outbox_dir=str(tmp_path / "pending"),
    )
    assert first == second
    assert first.stat().st_mode & 0o077 == 0


def test_security_delivery_overlay_binds_only_receipt_hashes():
    record = {
        "route": "security-preflight/security_preflight",
        "delivery_status": "delivered",
        "delivery_recorded_at": "2026-08-04T15:00:01+00:00",
    }
    result = {
        "status": "ok",
        "receipt": {
            "receipt_id": "vsr_example",
            "evidence_sha256": "c" * 64,
        },
    }
    bind_security_preflight_delivery(
        record,
        result,
        asset="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    )
    assert record["result_receipt_id"] == "vsr_example"
    assert len(record["result_artifact_sha256"]) == 64
    assert len(record["delivery_evidence_sha256"]) == 64
    assert "receipt" not in record


def test_self_settlement_cannot_be_exported():
    record = settlement()
    record["self_settle"] = True
    with pytest.raises(exporter.CommercialExportError):
        exporter.build_commercial_export(
            record,
            private_key_pkcs8_b64=private_key_b64(),
            key_id="fleet-commercial-v1",
        )
