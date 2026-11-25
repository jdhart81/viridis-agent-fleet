"""Pass badges (I2), badge privacy (I6) and the free-scan server key (I1)."""
import asyncio
import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src import core as C


def run(core, payload):
    return asyncio.run(core.process(payload))


def payload(endpoint="https://buyer.example/mcp", unsafe=False, **extra):
    tool = {"name": "read_status", "input_schema": {
        "type": "object", "properties": {"id": {"type": "string"}},
        "required": ["id"], "additionalProperties": False}}
    if unsafe:
        tool = {"name": "delete_everything", "input_schema": {"type": "object"}}
    manifest = {"auth": "bearer", "tools": [tool]}
    if endpoint is not None:
        manifest["endpoint"] = endpoint
    return {"action": "scan", "agent_id": "buyer-safe-agent", "manifest": manifest,
            "policy": {"allowed_tools": [tool["name"]], "denied_tools": [],
                       "approval_required_tools": []},
            "sample_inputs": ["Summarize the supplied status record."], **extra}


@pytest.fixture
def core():
    c = C.SecurityPreflightCore()
    yield c
    c.close()


def test_pass_issues_badge_with_markdown_and_urls(core):
    out = run(core, payload())
    assert out["status"] == "ok" and out["verdict"] == "pass"
    b = out["badge"]
    rid = out["receipt"]["receipt_id"]
    base = "https://mcp.viridis-security.com/security-preflight"
    assert b["svg_url"] == f"{base}/badge/{rid}.svg"
    assert b["verify_url"] == f"{base}/verify/{rid}"
    assert b["markdown"] == f"[![Preflight passed · Viridis Security]({base}/badge/{rid}.svg)]({base}/verify/{rid})"
    v = core.badge_view(rid)
    assert v == {"state": "passed", "receipt_id": rid, "server": "https://buyer.example/mcp",
                 "date": out["receipt"]["issued_at"][:10]}


def test_failed_or_review_scans_get_no_badge(core):
    out = run(core, payload(unsafe=True))
    assert out["status"] == "ok" and out["verdict"] != "pass"
    assert out["badge"] is None
    assert core.badge_view(out["receipt"]["receipt_id"]) == {"state": "not_verified"}


def test_unknown_or_malformed_ids_are_not_verified(core):
    for rid in ["vsr_" + "0" * 24, "vsr_xyz", "", None, "../etc", "vsr_" + "a" * 25, 7]:
        assert core.badge_view(rid) == {"state": "not_verified"}


def _tamper(core, rid, fn):
    row = core._receipt_db.execute(
        "SELECT record_json FROM security_preflight_badges WHERE receipt_id=?", (rid,)).fetchone()
    rec = json.loads(row[0]); fn(rec)
    core._receipt_db.execute("UPDATE security_preflight_badges SET record_json=? WHERE receipt_id=?",
                             (json.dumps(rec), rid))
    core._receipt_db.commit()


@pytest.mark.parametrize("mutate", [
    lambda r: r["badge"].__setitem__("server", "https://evil.example"),
    lambda r: r["badge"].__setitem__("date", "2099-01-01"),
    lambda r: r["badge"].__setitem__("findings", "x"),
    lambda r: r.__setitem__("signature_b64", r["signature_b64"][:-3] + ("AAA" if not r["signature_b64"].endswith("AAA") else "BBB")),
])
def test_tampered_badge_is_not_verified(core, mutate):
    rid = run(core, payload())["receipt"]["receipt_id"]
    _tamper(core, rid, mutate)
    assert core.badge_view(rid)["state"] == "not_verified"


def test_badge_signed_by_another_key_is_not_verified(core, monkeypatch):
    rid = run(core, payload())["receipt"]["receipt_id"]
    other = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    monkeypatch.setenv("SECURITY_PREFLIGHT_SIGNING_KEY_PKCS8_B64", base64.b64encode(other).decode())
    assert core.badge_view(rid)["state"] == "not_verified"


def test_badge_record_holds_only_server_date_result_id(core):
    out = run(core, payload(endpoint="https://user:pw@Buyer.Example:443/mcp/?token=secret#frag"))
    rid = out["receipt"]["receipt_id"]
    row = core._receipt_db.execute(
        "SELECT record_json FROM security_preflight_badges WHERE receipt_id=?", (rid,)).fetchone()
    rec = json.loads(row[0])["badge"]
    assert set(rec) == {"protocol", "receipt_id", "server", "date", "result"}
    assert rec["server"] == "https://buyer.example/mcp"
    blob = row[0] + json.dumps(core.badge_view(rid))
    for secret in ["user", "pw", "token", "secret", "frag", "buyer-safe-agent", "read_status", "bearer"]:
        assert secret not in blob.replace("buyer.example", "")


def test_no_endpoint_means_no_badge_but_scan_still_succeeds(core):
    out = run(core, payload(endpoint=None))
    assert out["status"] == "ok" and out["badge"] is None


@pytest.mark.parametrize("raw,expected", [
    ("https://A.example/mcp/", "https://a.example/mcp"),
    ("HTTPS://a.example:443/mcp?x=1#y", "https://a.example/mcp"),
    ("http://a.example:8080/", "http://a.example:8080"),
    ("ftp://a.example", None), ("javascript:alert(1)", None), ("", None), (None, None),
    ("https://a.example/<script>", None), ("https://" + "a" * 600 + ".example", None),
])
def test_normalize_server_url(raw, expected):
    assert C.normalize_server_url(raw) == expected


def test_server_key_prefers_url_then_manifest_digest():
    assert C.server_key(payload("https://A.example/mcp/")) == C.server_key(payload("https://a.example/mcp?q=1"))
    assert C.server_key(payload("https://a.example/mcp")) != C.server_key(payload("https://b.example/mcp"))
    k1 = C.server_key({"manifest": {"tools": [], "auth": "none"}})
    k2 = C.server_key({"manifest": {"auth": "none", "tools": []}})
    assert k1 == k2 and k1.startswith("manifest:")
    assert C.server_key({"manifest": "nope"}) is None
