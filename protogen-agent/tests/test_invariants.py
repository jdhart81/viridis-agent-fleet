"""Spec-invariance tests for protogen-agent (P1-P6). One test per invariant."""
import pytest
from src.core import ProtoGenCore


@pytest.fixture
def core():
    return ProtoGenCore()


async def test_P1_never_raises_error_envelope(core):
    r = await core.process({"name": "widget"})  # invalid spec: missing fields
    assert r["status"] == "error"
    assert "error_type" in r and "field" in r and "timestamp" in r


async def test_P2_cad_lifecycle_composes(core):
    ws = await core.process({
        "action": "create_cad_workspace", "project_name": "inv",
        "owner_agent": "test", "design_goal": "bracket",
    })
    assert ws["status"] == "success"
    d = await core.process({
        "action": "generate_cad_design",
        "workspace_id": ws["workspace"]["workspace_id"],
        "part_name": "bracket",
        "dimensions_mm": {"length": 10, "width": 20, "height": 3},
    })
    assert d["status"] == "success"
    e = await core.process({
        "action": "export_cad_design",
        "design_id": d["design"]["design_id"],
        "export_format": "openscad",
    })
    assert e["status"] == "success"
    assert e["export"]["content"]


async def test_P3_export_unknown_design_error(core):
    r = await core.process({"action": "export_cad_design", "design_id": "nope"})
    assert r["status"] == "error"


async def test_P4_design_dimension_validation(core):
    ws = await core.process({
        "action": "create_cad_workspace", "project_name": "inv2",
        "owner_agent": "test", "design_goal": "plate",
    })
    r = await core.process({
        "action": "generate_cad_design",
        "workspace_id": ws["workspace"]["workspace_id"],
        "part_name": "plate", "dimensions_mm": {"width": 20},  # missing length
    })
    assert r["status"] == "error"


@pytest.mark.parametrize("poison", [
    float("inf"), float("-inf"), float("nan"),
])
async def test_P4_non_finite_dimensions_fail_closed(core, poison):
    ws = await core.process({
        "action": "create_cad_workspace", "project_name": "finite",
        "owner_agent": "test", "design_goal": "plate",
    })
    r = await core.process({
        "action": "generate_cad_design",
        "workspace_id": ws["workspace"]["workspace_id"],
        "part_name": "plate",
        "dimensions_mm": {
            "length": poison, "width": 20, "height": 2,
        },
    })
    assert r["status"] == "error"
    assert "finite" in r["message"]


async def test_P5_describe_health_consistent(core):
    d = core.describe()
    h = core.health()
    assert d["name"] == h["agent"]
    assert d["capabilities"], "capabilities must be non-empty"


async def test_P6_process_is_total(core):
    for payload in [{}, {"action": None}, {"action": 42}, {"spec": "garbage"}]:
        r = await core.process(payload)
        assert isinstance(r, dict) and "status" in r
