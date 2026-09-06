"""The repeat trigger requires authentic, current, completely bound evidence."""
import asyncio
import base64
import copy
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.testclient import TestClient

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import preflight_watch as watch

spec = importlib.util.spec_from_file_location(
    "watch_security_core", HERE.parent / "security-preflight-agent/src/core.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def core(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    encoded = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    monkeypatch.setenv("SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64", base64.b64encode(encoded).decode())
    value = module.SecurityPreflightCore(str(tmp_path / "receipts.db"))
    yield value
    value.close()


def inputs():
    return {"agent_id": "customer-agent", "manifest": {
        "endpoint": "https://customer.example/mcp", "auth": "bearer",
        "tools": [{"name": "read_status", "input_schema": {
            "type": "object", "properties": {}, "additionalProperties": False}}]},
        "policy": {"allowed_tools": ["read_status"]}, "sample_inputs": ["ordinary sample"]}


def scan(core, value):
    result = asyncio.run(core.process(value))
    assert result["status"] == "ok"
    return result


def test_initial_check_is_free_and_never_creates_a_baseline(core):
    before = core._stored_receipt_count()
    result = watch.plan(core, {"inputs": inputs()}, "https://mcp.test")
    assert result["decision"] == "BASELINE_REQUIRED"
    assert result["quote_request"]["body"] == inputs()
    assert result["payment_authorized"] is False
    assert result["tool_executed"] is False
    assert core._stored_receipt_count() == before


def test_unchanged_baseline_survives_restart_and_does_not_quote(core):
    record = scan(core, inputs())
    database = core._receipt_db_path
    core.close()
    restored = module.SecurityPreflightCore(database)
    try:
        result = watch.plan(restored, {"inputs": inputs(),
            "baseline_receipt_id": record["receipt"]["receipt_id"]}, "https://mcp.test")
        assert result["decision"] == "UNCHANGED"
        assert result["quote_request"] is None
        assert result["runtime_execution_authorized"] is False
        assert restored._stored_receipt_count() == 1
    finally:
        restored.close()


@pytest.mark.parametrize("field", ["manifest", "policy", "sample_inputs", "subject_profile_sha256"])
def test_every_relevant_input_change_triggers_recheck(core, field):
    value = inputs()
    record = scan(core, value)
    changed = copy.deepcopy(value)
    if field == "sample_inputs":
        changed[field] = ["different sample, same list length"]
    elif field == "subject_profile_sha256":
        changed[field] = "a" * 64
    else:
        changed[field]["new_field"] = True
    result = watch.plan(core, {"inputs": changed,
        "baseline_receipt_id": record["receipt"]["receipt_id"]}, "https://mcp.test")
    assert result["decision"] == "RECHECK_REQUIRED"
    assert "inputs_changed" in result["reasons"]
    assert result["quote_request"]["body"] == changed
    assert result["quote_request"]["auto_pay"] is False


def test_expired_and_changed_scanner_require_fresh_assessment(core, monkeypatch):
    record = scan(core, inputs())
    payload = {"inputs": inputs(), "baseline_receipt_id": record["receipt"]["receipt_id"]}
    expired = datetime.fromisoformat(record["receipt"]["expires_at"].replace("Z", "+00:00"))
    assert "assessment_expired" in watch.plan(core, payload, "https://mcp.test", now=expired)["reasons"]
    monkeypatch.setattr(module, "VERSION", "future-scanner")
    assert "scanner_changed" in watch.plan(core, payload, "https://mcp.test")["reasons"]


def test_existing_findings_are_preserved_when_inputs_are_unchanged(core):
    value = inputs()
    value["manifest"]["tools"][0]["name"] = "delete_account"
    record = scan(core, value)
    result = watch.plan(core, {"inputs": value,
        "baseline_receipt_id": record["receipt"]["receipt_id"]}, "https://mcp.test")
    assert result["decision"] == "UNCHANGED"
    assert result["baseline"]["verdict"] == "fail"
    assert result["runtime_execution_authorized"] is False


def test_subject_mismatch_unknown_and_corrupted_evidence_fail_closed(core, monkeypatch):
    record = scan(core, inputs())
    payload = {"inputs": inputs(), "baseline_receipt_id": record["receipt"]["receipt_id"]}
    payload["inputs"]["agent_id"] = "another-agent"
    with pytest.raises(ValueError, match="different agent"):
        watch.plan(core, payload, "https://mcp.test")
    with pytest.raises(LookupError):
        watch.plan(core, {"inputs": inputs(), "baseline_receipt_id": "vsr_" + "0" * 24}, "https://mcp.test")
    corrupted = copy.deepcopy(record)
    corrupted["evidence"]["verdict"] = "tampered"
    monkeypatch.setattr(core, "_get_receipt", lambda _: corrupted)
    with pytest.raises(RuntimeError, match="integrity"):
        watch.plan(core, {"inputs": inputs(), "baseline_receipt_id": record["receipt"]["receipt_id"]}, "https://mcp.test")


@pytest.mark.parametrize("value", [{"inputs": {}, "auto_pay": True},
                                 {"inputs": {**inputs(), "extra": True}},
                                 {"inputs": {**inputs(), "manifest": {"x": float('nan')}}}])
def test_invalid_or_non_finite_inputs_never_run(core, value):
    with pytest.raises(ValueError):
        watch.plan(core, value, "https://mcp.test")
    assert core._stored_receipt_count() == 0


def test_public_http_factories_use_a_signed_persisted_baseline(core):
    from starlette.applications import Starlette
    from starlette.routing import Route
    record = scan(core, inputs())
    receipt_id = record["receipt"]["receipt_id"]
    app = Starlette(routes=[
        Route(watch.PATH, watch.make_watch_route({"security-preflight": core}, "https://mcp.test"), methods=["POST"]),
        Route(watch.RECEIPT_PATH, watch.make_receipt_route({"security-preflight": core}), methods=["GET"]),
    ])
    with TestClient(app) as client:
        response = client.post(watch.PATH, json={"inputs": inputs(), "baseline_receipt_id": receipt_id})
        assert response.status_code == 200
        assert response.json()["decision"] == "UNCHANGED"
        public = client.get(watch.RECEIPT_PATH.format(receipt_id=receipt_id))
        assert public.status_code == 200
        assert public.json()["signature_b64"] == record["signature_b64"]
        assert "feedback_token" not in public.text
        assert client.post(watch.PATH, json={"inputs": {}}).status_code == 400
        assert client.get(watch.RECEIPT_PATH.format(receipt_id="vsr_" + "0" * 24)).status_code == 404


def test_public_discovery_declares_no_automatic_purchase():
    info = watch.discovery("https://mcp.test")
    assert info["endpoint"] == "https://mcp.test" + watch.PATH
    assert info["buyer_owns_schedule"] is True
    assert info["managed_subscription_active"] is False
    assert info["auto_pay"] is False
