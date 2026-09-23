"""Spec-invariance tests for narrative-engine-agent (N1-N6). One test per invariant."""
import inspect
import pytest
import src.core as core_mod

CoreCls = [v for k, v in vars(core_mod).items()
           if inspect.isclass(v) and k.endswith("Core")][-1]

VALID = {
    "action": "translate",
    "agent_output": {"biodiversity_score": 0.82, "ecosystem_type": "temperate_forest"},
    "audience_type": "grant_funder",
    "format_type": "grant_proposal",
}


@pytest.fixture
def core():
    return CoreCls()


async def test_N1_empty_agent_output_validation_error(core):
    r = await core.process({"action": "translate"})
    assert r["status"] == "error"
    assert r["error_type"] == "ValidationError"
    assert "timestamp" in r


async def test_N2_unknown_action_names_supported(core):
    r = await core.process({"action": "__nope__"})
    assert r["status"] == "error"
    assert "translate" in r["message"]


async def test_N3_audience_closed_vocabulary(core):
    r = await core.process({**VALID, "audience_type": "space_alien"})
    assert r["status"] == "error"
    assert r["error_type"] == "ValidationError"
    assert "grant_funder" in r["message"]  # names valid values


async def test_N4_valid_translate_returns_narrative(core):
    r = await core.process(VALID)
    assert r["status"] == "success"
    res = r["result"]
    assert res["title"] and res["content"]
    assert 0.0 <= res["quality_score"] <= 1.0
    assert res["audience"] == "grant_funder"


async def test_N5_describe_health_consistent(core):
    d = core.describe()
    h = await core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"], "capabilities must be non-empty"


async def test_N6_process_is_total(core):
    for payload in [{}, {"action": None}, {"action": 42}, {"agent_output": "x"}]:
        r = await core.process(payload)
        assert isinstance(r, dict) and "status" in r
