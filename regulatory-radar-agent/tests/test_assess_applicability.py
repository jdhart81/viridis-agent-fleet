"""Invariant A6 for assess_compliance and B1 build identity (2026-11-03).

A6a A size-gated binding entry with no annual_revenue_usd is listed under
    applicability_unconfirmed, is neither met nor a gap, and the overall level
    is never "compliant".
A6b Revenue below the gate lists the entry under out_of_scope (no gap, not counted).
A6c Revenue at or above the gate assesses the entry as before (gaps or met).
A6d annual_revenue_usd must be a finite, non-negative number.
B1  describe() reports a build block from VIRIDIS_BUILD_SHA, never a guess.
"""
import json

import pytest

from src.core import RegulatoryRadarCore, build_info

SB253 = "ca-sb253-2026"
COVERED = ["GHG Protocol", "Scope 1", "Scope 2"]


async def _assess(**kw):
    payload = {"action": "assess", "company_name": "T", "sector": "manufacturing",
               "jurisdiction": "california", **kw}
    r = await RegulatoryRadarCore().process(payload)
    assert r["status"] == "success", r
    return r["result"]


def _ids(rows, key="regulation_id"):
    return {row[key] for row in rows}


async def test_A6a_unknown_size_is_never_compliant():
    # The live overclaim: these disclosures and no revenue used to return
    # "compliant", 100%.
    res = await _assess(disclosures=COVERED)
    assert res["overall_compliance_level"] != "compliant"
    assert res["overall_compliance_level"] == "undetermined"
    assert SB253 in _ids(res["applicability_unconfirmed"])
    assert SB253 not in _ids(res["gaps"])
    assert res["compliance_percentage"] is None
    assert res["binding_obligations_assessed"] == 0
    assert "annual_revenue_usd" in res["summary"]
    json.dumps(res)


async def test_A6a_without_disclosures_also_unconfirmed():
    res = await _assess()
    assert SB253 in _ids(res["applicability_unconfirmed"])
    assert SB253 not in _ids(res["gaps"])
    assert res["overall_compliance_level"] == "undetermined"


async def test_A6b_below_gate_is_out_of_scope():
    res = await _assess(annual_revenue_usd=25_000_000)
    assert SB253 in _ids(res["out_of_scope"])
    assert SB253 not in _ids(res["gaps"])
    assert SB253 not in _ids(res["applicability_unconfirmed"])
    assert res["annual_revenue_usd"] == 25_000_000


async def test_A6c_at_gate_is_assessed():
    gap = await _assess(annual_revenue_usd=1_000_000_000)
    assert SB253 in _ids(gap["gaps"])
    assert gap["overall_compliance_level"] in ("partial", "non_compliant")
    met = await _assess(annual_revenue_usd=1_500_000_000, disclosures=[SB253])
    assert SB253 not in _ids(met["gaps"])
    assert met["overall_compliance_level"] == "compliant"
    assert met["applicability_unconfirmed"] == []


@pytest.mark.parametrize("bad", [-1, "1e9", True, float("nan"), float("inf")])
async def test_A6d_bad_revenue_is_rejected(bad):
    r = await RegulatoryRadarCore().process(
        {"action": "assess", "company_name": "T", "sector": "manufacturing",
         "jurisdiction": "california", "annual_revenue_usd": bad})
    assert r["status"] == "error", r


async def test_A6_mcp_argument_is_honoured():
    from adapters import mcp_server
    out = json.loads(await mcp_server.assess_compliance(
        "T", "manufacturing", "california", annual_revenue_usd=25_000_000))
    assert SB253 in _ids(out["result"]["out_of_scope"])


def test_B1_build_info(monkeypatch):
    monkeypatch.delenv("VIRIDIS_BUILD_SHA", raising=False)
    assert build_info() == {"git_sha": None, "status": "not_set",
                            "source": "env:VIRIDIS_BUILD_SHA"}
    monkeypatch.setenv("VIRIDIS_BUILD_SHA", "7C16107E00D0A052C92F24800299F34B103BDEB4")
    assert build_info()["git_sha"] == "7c16107e00d0a052c92f24800299f34b103bdeb4"
    assert build_info()["status"] == "reported"
    monkeypatch.setenv("VIRIDIS_BUILD_SHA", "main; rm -rf /")
    assert build_info() == {"git_sha": None, "status": "invalid",
                            "source": "env:VIRIDIS_BUILD_SHA"}
    monkeypatch.setenv("VIRIDIS_BUILD_SHA", "abc1234")
    assert RegulatoryRadarCore().describe()["build"]["git_sha"] == "abc1234"
