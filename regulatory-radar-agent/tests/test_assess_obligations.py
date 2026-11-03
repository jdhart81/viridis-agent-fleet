"""Invariants A1-A5 for assess_compliance (directory-review fixes, 2026-11-02).

A1 Only binding obligations produce gaps / count toward the percentage.
A2 process() returns a JSON-safe structured dict (no Python repr strings).
A3 Past key dates are overdue (never "due in N days"); critical = binding, 0-89 days ahead.
A4 priority_actions carry the gap's real risk level.
A5 `disclosures` satisfy matching requirements (ids, standards, requirement text).

SB 253 is revenue-gated (A6, test_assess_applicability.py), so tests that
need it assessed supply a covered annual revenue.
"""
import json
from datetime import datetime, timedelta

from src.core import (RegulatoryRadarCore, Jurisdiction, Sector, obligation_class)

COVERED_REVENUE = 1_500_000_000  # above SB 253's $1B gate


def core():
    return RegulatoryRadarCore()


async def _assess(c, **kw):
    payload = {"action": "assess", "company_name": "T", "sector": "energy",
               "jurisdiction": "california", **kw}
    r = await c.process(payload)
    assert r["status"] == "success", r
    return r["result"]


async def test_A1_non_binding_never_gaps():
    c = core()
    res = await _assess(c)
    by_id = {r.id: r for r in c.db.get_regulations_by_jurisdiction(Jurisdiction.CALIFORNIA)}
    for g in res["gaps"]:
        assert obligation_class(by_id[g["regulation_id"]]) == "binding", g
    context_ids = {x["regulation_id"] for x in res["not_currently_binding"]}
    # SEC rule is stayed, SB 261 enforcement enjoined, TNFD voluntary.
    assert {"sec-climate-disclosure-2023", "ca-sb261-2026", "tnfd-disclosure-2024"} <= context_ids
    assert not context_ids & {g["regulation_id"] for g in res["gaps"]}


async def test_A2_json_safe_structured():
    res = await _assess(core())
    assert isinstance(res, dict)
    json.dumps(res)  # must not raise
    for key in ("overall_compliance_level", "compliance_percentage", "gaps",
                "priority_actions", "not_currently_binding", "applicable_regulations"):
        assert key in res
    assert "ComplianceAssessment(" not in json.dumps(res)


async def test_A3_past_binding_is_overdue_not_due(monkeypatch):
    c = core()
    regs = c.db.get_regulations_by_jurisdiction(Jurisdiction.CALIFORNIA)
    sb253 = next(r for r in regs if r.id == "ca-sb253-2026")
    monkeypatch.setattr(sb253, "reporting_deadline", datetime.utcnow() - timedelta(days=12))
    a = await c.assess_compliance("T", Jurisdiction.CALIFORNIA, Sector.ENERGY, {},
                                  annual_revenue_usd=COVERED_REVENUE)
    g = next(g for g in a.gaps if g.regulation_id == "ca-sb253-2026")
    assert g.deadline_status == "past" and g.deadline_days < 0
    assert g.risk_level != "critical"
    action = next(x for x in a.priority_actions if "SB 253" in x)
    assert "overdue" in action and "due in" not in action


async def test_A3_upcoming_binding_within_90_is_critical():
    a = await core().assess_compliance("T", Jurisdiction.CALIFORNIA, Sector.ENERGY, {},
                                       annual_revenue_usd=COVERED_REVENUE)
    for g in a.gaps:
        if g.deadline_status == "upcoming" and g.deadline_days < 90:
            assert g.risk_level == "critical"
        if g.risk_level == "critical":
            assert g.deadline_status in ("upcoming", "due_today") and g.deadline_days < 90


async def test_A4_action_label_matches_risk():
    a = await core().assess_compliance("T", Jurisdiction.EU, Sector.MANUFACTURING, {})
    for action in a.priority_actions:
        g = next(g for g in a.gaps if g.regulation_name in action)
        assert action.startswith(f"[{g.risk_level.upper()}]")


async def test_A5_disclosures_satisfy_requirements():
    c = core()
    base = await _assess(c, annual_revenue_usd=COVERED_REVENUE)
    covered = await _assess(c, disclosures=["ca-sb253-2026"],
                            annual_revenue_usd=COVERED_REVENUE)
    assert any(g["regulation_id"] == "ca-sb253-2026" for g in base["gaps"])
    assert not any(g["regulation_id"] == "ca-sb253-2026" for g in covered["gaps"])
    assert covered["compliance_percentage"] > base["compliance_percentage"]


async def test_mcp_tool_returns_json_object():
    from adapters import mcp_server
    out = await mcp_server.assess_compliance("T", "energy", "california")
    body = json.loads(out)
    assert isinstance(body["result"], dict)


async def test_tool_hints_match_behavior():
    from adapters import mcp_server
    if mcp_server.HAS_MCP:   # real SDK: public list_tools API
        anns = {t.name: t.annotations for t in await mcp_server.mcp.list_tools()}
    else:                    # stdlib shim records the declared annotations
        anns = {n: fn.__mcp_annotations__ for n, fn in mcp_server.mcp.tools.items()}

    def h(n):
        a = anns[n]
        return a if isinstance(a, dict) else a.model_dump(by_alias=True, exclude_none=True)
    for n in ("scan_regulations", "monitor_changes", "assess_compliance", "describe_agent"):
        assert h(n)["readOnlyHint"] is True and h(n)["openWorldHint"] is False, n
    ep = h("build_evidence_pack")
    assert ep["readOnlyHint"] is False and ep["destructiveHint"] is False and ep["openWorldHint"] is True
