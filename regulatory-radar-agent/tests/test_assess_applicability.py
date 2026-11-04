"""Invariant A6 for assess_compliance and B1 build identity.

SB 253 applicability (17 CCR 96071-96072, Health & Safety Code 38532(b)(2)):
A6a With applicability inputs missing, SB 253 is listed under
    applicability_unconfirmed, is neither met nor a gap, and the overall level
    is "undetermined", never "compliant". The summary and the row name the
    missing inputs.
A6b Revenue at or below $1B in either previous fiscal year puts it out of
    scope (strictly greater than; lesser of two years).
A6c Revenue over $1B in both years plus a covered entity assesses it as
    before (gaps or met).
A6d Revenue inputs must be finite and non-negative; entity_profile fields are
    validated.
A6e One year over $1B with the other unknown is unconfirmed (two-year rule).
A6f Each entity condition: unknown -> unconfirmed; failing -> out of scope.
A6g A definite out-of-scope reason wins over missing inputs.
A6h The assessment is labelled screening only.
B1  describe() reports a build block from VIRIDIS_BUILD_SHA, never a guess.
"""
import json

import pytest

from src.applicability import EXEMPTIONS, evaluate_gate
from src.core import RegulatoryRadarCore, build_info

SB253 = "ca-sb253-2026"
COVERED = ["GHG Protocol", "Scope 1", "Scope 2"]
ENTITY = {"entity_form": "corporation", "formed_under_us_law": True,
          "does_business_in_california": True, "exemption": "none"}
IN_SCOPE = {"annual_revenue_usd": 1_500_000_000,
            "prior_year_revenue_usd": 1_200_000_000, "entity_profile": ENTITY}


async def _assess(**kw):
    payload = {"action": "assess", "company_name": "T", "sector": "manufacturing",
               "jurisdiction": "california", **kw}
    r = await RegulatoryRadarCore().process(payload)
    assert r["status"] == "success", r
    return r["result"]


def _ids(rows, key="regulation_id"):
    return {row[key] for row in rows}


def _row(rows):
    return next(row for row in rows if row["regulation_id"] == SB253)


def _sb253_gate():
    db = RegulatoryRadarCore().db
    return db.regulations["ca-sb253-first-filing-2026"].applicability_gate


async def test_A6a_unknown_size_is_never_compliant():
    # The live overclaim: these disclosures and no revenue used to return
    # "compliant", 100%.
    res = await _assess(disclosures=COVERED)
    assert res["overall_compliance_level"] == "undetermined"
    assert SB253 in _ids(res["applicability_unconfirmed"])
    assert SB253 not in _ids(res["gaps"])
    assert res["compliance_percentage"] is None
    assert res["binding_obligations_assessed"] == 0
    row = _row(res["applicability_unconfirmed"])
    assert row["missing_inputs"] == [
        "annual_revenue_usd", "prior_year_revenue_usd",
        "entity_profile.entity_form", "entity_profile.formed_under_us_law",
        "entity_profile.does_business_in_california", "entity_profile.exemption"]
    for name in row["missing_inputs"]:
        assert name in res["summary"]
    assert row["revenue_exceeds_usd"] == 1_000_000_000
    assert row["revenue_fiscal_years"] == 2
    assert "96072" in row["applicability_citation"]
    json.dumps(res)


async def test_A6a_revenue_alone_is_not_enough():
    # PR 138 counted SB 253 on revenue alone; entity conditions now required.
    res = await _assess(annual_revenue_usd=1_500_000_000,
                        prior_year_revenue_usd=1_500_000_000, disclosures=[SB253])
    assert SB253 in _ids(res["applicability_unconfirmed"])
    assert res["overall_compliance_level"] == "undetermined"
    assert all(m.startswith("entity_profile.")
               for m in _row(res["applicability_unconfirmed"])["missing_inputs"])


@pytest.mark.parametrize("annual,prior", [
    (1_000_000_000, 2_000_000_000),   # exactly $1B is not "in excess of"
    (2_000_000_000, 1_000_000_000),   # lesser year decides
    (25_000_000, None),               # one low year settles it
    (None, 999_999_999),
])
async def test_A6b_at_or_below_threshold_is_out_of_scope(annual, prior):
    kw = {"entity_profile": ENTITY}
    if annual is not None:
        kw["annual_revenue_usd"] = annual
    if prior is not None:
        kw["prior_year_revenue_usd"] = prior
    res = await _assess(**kw)
    assert SB253 in _ids(res["out_of_scope"])
    assert SB253 not in _ids(res["gaps"])
    assert SB253 not in _ids(res["applicability_unconfirmed"])
    assert "not more than the $1,000,000,000 threshold" in _row(res["out_of_scope"])["reason"]


async def test_A6c_in_scope_is_assessed():
    gap = await _assess(**IN_SCOPE)
    assert SB253 in _ids(gap["gaps"])
    assert gap["overall_compliance_level"] in ("partial", "non_compliant")
    met = await _assess(disclosures=[SB253], **IN_SCOPE)
    assert SB253 not in _ids(met["gaps"])
    assert met["overall_compliance_level"] == "compliant"
    assert met["applicability_unconfirmed"] == []
    assert met["out_of_scope"] == []
    assert met["prior_year_revenue_usd"] == 1_200_000_000
    assert met["entity_profile"] == ENTITY


async def test_A6c_just_over_threshold_counts():
    res = await _assess(annual_revenue_usd=1_000_000_001,
                        prior_year_revenue_usd=1_000_000_001, entity_profile=ENTITY)
    assert SB253 in _ids(res["gaps"])


@pytest.mark.parametrize("field,bad", [
    ("annual_revenue_usd", -1), ("annual_revenue_usd", "1e9"),
    ("annual_revenue_usd", True), ("annual_revenue_usd", float("nan")),
    ("annual_revenue_usd", float("inf")),
    ("prior_year_revenue_usd", -1), ("prior_year_revenue_usd", "1e9"),
    ("prior_year_revenue_usd", False), ("prior_year_revenue_usd", float("inf")),
    ("entity_profile", "corporation"),
    ("entity_profile", {"entity_form": "trust"}),
    ("entity_profile", {"formed_under_us_law": "yes"}),
    ("entity_profile", {"does_business_in_california": 1}),
    ("entity_profile", {"exemption": "small_business"}),
    ("entity_profile", {"employees": 10}),
])
async def test_A6d_bad_inputs_are_rejected(field, bad):
    r = await RegulatoryRadarCore().process(
        {"action": "assess", "company_name": "T", "sector": "manufacturing",
         "jurisdiction": "california", field: bad})
    assert r["status"] == "error", r


@pytest.mark.parametrize("kw,missing", [
    ({"annual_revenue_usd": 1_500_000_000}, "prior_year_revenue_usd"),
    ({"prior_year_revenue_usd": 1_500_000_000}, "annual_revenue_usd"),
])
async def test_A6e_one_year_over_threshold_is_unconfirmed(kw, missing):
    res = await _assess(entity_profile=ENTITY, **kw)
    assert _row(res["applicability_unconfirmed"])["missing_inputs"] == [missing]
    assert res["overall_compliance_level"] == "undetermined"


@pytest.mark.parametrize("cond", ["entity_form", "formed_under_us_law",
                                  "does_business_in_california", "exemption"])
async def test_A6f_unknown_entity_condition_is_unconfirmed(cond):
    profile = {k: v for k, v in ENTITY.items() if k != cond}
    res = await _assess(**{**IN_SCOPE, "entity_profile": profile})
    row = _row(res["applicability_unconfirmed"])
    assert row["missing_inputs"] == [f"entity_profile.{cond}"]
    assert SB253 not in _ids(res["gaps"])


@pytest.mark.parametrize("override,phrase", [
    ({"formed_under_us_law": False}, "not formed under the law of a US state"),
    ({"does_business_in_california": False}, "does not do business in California"),
] + [({"exemption": e}, "exempt:") for e in EXEMPTIONS if e != "none"])
async def test_A6f_failing_entity_condition_is_out_of_scope(override, phrase):
    res = await _assess(**{**IN_SCOPE, "entity_profile": {**ENTITY, **override}})
    assert SB253 in _ids(res["out_of_scope"])
    assert phrase in _row(res["out_of_scope"])["reason"]
    assert SB253 not in _ids(res["gaps"])


async def test_A6g_out_of_scope_wins_over_missing_inputs():
    res = await _assess(annual_revenue_usd=10_000_000)
    assert SB253 in _ids(res["out_of_scope"])
    assert SB253 not in _ids(res["applicability_unconfirmed"])
    verdict = evaluate_gate(_sb253_gate(), None, None,
                            {"exemption": "tax_exempt_nonprofit"})
    assert verdict["status"] == "out_of_scope"


def test_A6_gate_revenue_basis_is_lesser_year():
    v = evaluate_gate(_sb253_gate(), 3_000_000_000, 1_100_000_000, ENTITY)
    assert v == {"status": "in_scope", "reasons": [], "missing_inputs": [],
                 "revenue_basis_usd": 1_100_000_000}


async def test_A6h_labelled_screening_only():
    res = await _assess(**IN_SCOPE)
    assert res["screening_only"] is True
    assert "not legal advice" in res["disclaimer"]


async def test_A6_mcp_arguments_are_honoured():
    from adapters import mcp_server
    out = json.loads(await mcp_server.assess_compliance(
        "T", "manufacturing", "california", annual_revenue_usd=25_000_000))
    assert SB253 in _ids(out["result"]["out_of_scope"])
    out = json.loads(await mcp_server.assess_compliance(
        "T", "manufacturing", "california", annual_revenue_usd=1_500_000_000,
        prior_year_revenue_usd=1_200_000_000, entity_profile=ENTITY))
    assert SB253 in _ids(out["result"]["gaps"])


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
