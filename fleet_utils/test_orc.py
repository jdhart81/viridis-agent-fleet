"""ORC v0.1 invariant tests (R1–R7) + conformance vectors."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fleet_utils import orc  # noqa: E402

VEC = ROOT / "docs" / "standards" / "orc" / "vectors.json"
ISS = {"id": "did:web:example.org", "name": "Example"}
SUB = {"agent": "demo", "tool": "echo"}


def _r(output=None, **kw):
    return orc.seal(output or {"amount_usd": "720000.00", "n": 3, "ok": True, "note": "Café ☀"},
                    issuer=ISS, subject=SUB, salt="ab" * 32,
                    issued_at="2026-09-24T00:00:00+00:00", **kw)


def test_r1_canonical_matches_engine_form():
    v = {"b": 1, "a": ["é", {"d": None, "c": "x"}]}
    assert orc.canonical(v) == '{"a":["\\u00e9",{"c":"x","d":null}],"b":1}'


def test_r2_seal_is_pure_and_deterministic():
    out = {"x": "1"}
    a, b = _r(dict(out)), orc.seal(dict(out), issuer=ISS, subject=SUB)
    assert a["digest"]["value"] == b["digest"]["value"]
    assert a["commitment"]["value"] != b["commitment"]["value"]
    src = {"x": "1"}; orc.seal(src, issuer=ISS, subject=SUB); assert src == {"x": "1"}


@pytest.mark.parametrize("bad", [None, 42, "x", [], {"orc": "9"}, {"orc": "0.1"},
                                 {"orc": "0.1", "digest": {}, "commitment": {}, "output": {}}])
def test_r3_verify_never_raises(bad):
    v = orc.verify(bad)
    assert v["level"] == 0 and v["reasons"]


def test_r4_l1_needs_digest_and_commitment():
    r = _r(); assert orc.verify(r)["level"] == 1
    t = json.loads(json.dumps(r)); t["output"]["amount_usd"] = "999999.00"
    assert orc.verify(t)["level"] == 0
    t = json.loads(json.dumps(r)); t["commitment"]["value"] = "0" * 64
    assert orc.verify(t)["level"] == 0
    t = json.loads(json.dumps(r)); t["digest"]["excludes"] = ["amount_usd"]
    assert orc.verify(t)["level"] == 0


def test_r5_levels_need_explicit_resolvers():
    r = _r()
    yes, no = (lambda _: True), (lambda _: False)
    assert orc.verify(r)["label"] == "INTACT"
    assert orc.verify(r, issuer_resolver=no)["level"] == 1
    assert orc.verify(r, issuer_resolver=yes)["level"] == 2
    assert orc.verify(r, issuer_resolver=yes, payment_resolver=yes)["level"] == 3
    v = orc.verify(r, issuer_resolver=yes, payment_resolver=yes, validation_resolver=yes)
    assert v["label"] == "VALIDATED"
    # a later resolver without an earlier one does not upgrade
    assert orc.verify(r, payment_resolver=yes)["level"] == 1


def test_r6_floats_rejected():
    with pytest.raises(ValueError):
        orc.seal({"amount": 1.5}, issuer=ISS, subject=SUB)


def test_r7_cliff_check_maps_losslessly():
    sys.path.insert(0, str(ROOT / "products" / "signed-cliff-check"))
    import build_report as br
    spec = json.loads((ROOT / "products/signed-cliff-check/sample_solar_48e.json").read_text())
    cc, _ = br.build(spec["credit"], spec["facts"], "C", "P", salt="cd" * 32)
    o = orc.from_cliff_check(json.loads(json.dumps(cc)))
    assert o["digest"]["value"] == cc["result"]["audit_sha256"]
    assert o["commitment"]["value"] == cc["signature"]["commit_hash"]
    assert orc.verify(o)["level"] == 1


def test_erc8004_mapping():
    r = _r()
    m = orc.erc8004_validation_response(r, request_hash="11" * 32,
                                        response_uri="https://x/orc.json", passed=True)
    assert m["responseHash"] == "0x" + r["commitment"]["value"] and m["response"] == 100
    assert m["tag"] == "orc/0.1"


def test_conformance_vectors():
    vec = json.loads(VEC.read_text())
    assert len(vec["vectors"]) >= 4
    for case in vec["vectors"]:
        assert orc.verify(case["receipt"])["level"] == case["expect_level"], case["name"]
