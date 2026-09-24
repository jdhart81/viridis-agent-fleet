"""Spec-invariance tests for regulatory-radar-agent (G1-G6). One test per invariant."""
import pytest
from src.core import RegulatoryRadarCore


@pytest.fixture
def core():
    return RegulatoryRadarCore()


async def test_G1_never_raises_full_envelope(core):
    r = await core.process({"action": "scan"})  # missing jurisdiction
    assert r["status"] == "error"
    for key in ("error_type", "field", "value", "constraint", "message", "timestamp"):
        assert key in r, f"envelope missing {key}"


async def test_G2_unknown_action_names_supported(core):
    r = await core.process({"action": "__nope__"})
    assert r["status"] == "error"
    assert "scan" in r["message"] and "assess" in r["message"]


async def test_G3_scan_returns_regulations(core):
    r = await core.process({"action": "scan", "jurisdiction": "EU"})
    assert r["status"] == "success"
    assert isinstance(r["regulations"], list)
    assert r["total_regulations"] >= r["urgent_count"] >= 0


async def test_G4_assess_returns_assessment(core):
    r = await core.process({
        "action": "assess", "company_name": "ACME",
        "sector": "manufacturing", "jurisdiction": "EU",
    })
    assert r["status"] == "success"
    assert "result" in r


async def test_G5_describe_health_consistent(core):
    d = core.describe()
    h = await core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"], "capabilities must be non-empty"


async def test_G6_health_exposes_regulation_count(core):
    h = await core.health()
    assert h["regulations_in_db"] >= 0
