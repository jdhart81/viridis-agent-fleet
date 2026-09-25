"""V1-V4 for the reference ORC replay validator."""
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "products" / "signed-cliff-check"))
import validator as v  # noqa: E402
import build_report as br  # noqa: E402
from fleet_utils import orc  # noqa: E402

SPEC = json.loads((ROOT / "products/signed-cliff-check/sample_solar_48e.json").read_text())
RH, URI = "22" * 32, "https://mcp.viridisconservation.com/orc/v0/commitments/x"


def _orc():
    cc, _ = br.build(SPEC["credit"], SPEC["facts"], "C", "P", today=date(2026, 9, 24),
                     salt="ab" * 32)
    return orc.from_cliff_check(json.loads(json.dumps(cc)))


def test_v1_v2_reproduced_is_100_and_matches_reference_mapping():
    r = _orc()
    out = v.validate(r, SPEC["facts"], request_hash=RH, response_uri=URI)
    assert out["replay"]["reason"] == "reproduced" and out["args"]["response"] == 100
    assert out["args"] == orc.erc8004_validation_response(
        r, request_hash=RH, response_uri=URI, passed=True)
    assert out["signed"] is False


def test_v1_wrong_facts_or_tamper_is_0():
    r = _orc()
    other = dict(SPEC["facts"], qualified_investment_usd="100")
    assert v.validate(r, other, request_hash=RH, response_uri=URI)["args"]["response"] == 0
    t = json.loads(json.dumps(r)); t["output"]["credit_amount_usd"] = "1.00"
    out = v.validate(t, SPEC["facts"], request_hash=RH, response_uri=URI)
    assert out["replay"]["reason"] == "not_intact" and out["args"]["response"] == 0


def test_v4_facts_required_and_unknown_profile():
    r = _orc()
    assert v.replay(r, None)["reason"] == "facts_required"
    g = orc.seal({"x": "1"}, issuer={"id": "did:web:x"}, subject={}, salt="cd" * 32)
    assert v.replay(g, {})["reason"] == "profile_not_replayable"


def test_v3_no_network(monkeypatch):
    import socket
    def boom(*a, **k):
        raise AssertionError("network")
    monkeypatch.setattr(socket.socket, "connect", boom)
    assert v.validate(_orc(), SPEC["facts"], request_hash=RH, response_uri=URI)["args"]["response"] == 100


def test_cli(tmp_path, capsys):
    p = tmp_path / "r.orc.json"; p.write_text(json.dumps(_orc()))
    f = tmp_path / "facts.json"; f.write_text(json.dumps(SPEC))
    assert v.main([str(p), "--facts", str(f), "--request-hash", "0x" + RH,
                   "--response-uri", URI]) == 0
    assert json.loads(capsys.readouterr().out)["args"]["response"] == 100
