"""Invariant tests for neurogenesis-agent (NG1-NG6) + fleet contract."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core import build

GENOME = {
    "agent_name": "test-sprout",
    "purpose": "prove developmental invariants",
    "initial_nodes": ["planner", "executor", "safety_checker"],
    "fitness_metrics": ["task_success"],
}

EVAL_OK = {"task_id": "t1", "task_type": "planning", "success_score": 0.9,
           "safety_score": 1.0, "used_nodes": ["planner", "executor"],
           "used_edges": [["planner", "executor"]]}


@pytest.fixture
def core():
    return build()


async def _create(core, genome=None):
    r = await core.process({"action": "create_agent",
                            "genome": genome or GENOME})
    assert r["status"] == "ok", r
    return r["data"]["agent_id"]


# --- NG2 genome validation -------------------------------------------------- #
async def test_NG2_valid_genome_creates_agent_with_graph(core):
    r = await core.process({"action": "create_agent", "genome": GENOME})
    assert r["status"] == "ok"
    assert r["data"]["nodes"] >= 3
    assert r["data"]["agent_id"].startswith("ng_")


async def test_NG2_invalid_genome_is_structured_error(core):
    r = await core.process({"action": "create_agent",
                            "genome": {"agent_name": "", "purpose": "x",
                                       "initial_nodes": [],
                                       "fitness_metrics": []}})
    assert r["status"] == "error"
    assert r["error_type"] == "ValidationError"


# --- NG1 evolution through the engine only ---------------------------------- #
async def test_NG1_evaluation_evolves_and_ledger_grows(core):
    aid = await _create(core)
    before = await core.process({"action": "get_ledger", "agent_id": aid})
    r = await core.process({"action": "submit_evaluation", "agent_id": aid,
                            "evaluation": EVAL_OK})
    assert r["status"] == "ok"
    assert r["data"]["evaluation_accepted"] is True
    assert r["data"]["is_success"] is True
    after = await core.process({"action": "get_ledger", "agent_id": aid})
    assert after["data"]["total_events"] > before["data"]["total_events"]


# --- NG3 ledger verbatim ----------------------------------------------------- #
async def test_NG3_ledger_is_append_only_record(core):
    aid = await _create(core)
    await core.process({"action": "submit_evaluation", "agent_id": aid,
                        "evaluation": EVAL_OK})
    ledger = await core.process({"action": "get_ledger", "agent_id": aid})
    events = ledger["data"]["events"]
    assert events[0]["event_type"] == "agent_initialized"
    assert all("reason" in e for e in events)


# --- NG4 state portability + persistence surface ----------------------------- #
async def test_NG4_export_import_roundtrip(core):
    aid = await _create(core)
    await core.process({"action": "submit_evaluation", "agent_id": aid,
                        "evaluation": EVAL_OK})
    exported = await core.process({"action": "export_state", "agent_id": aid})
    assert exported["status"] == "ok"
    imported = await core.process({"action": "import_state",
                                   "state": exported["data"]["state"]})
    assert imported["status"] == "ok"
    a = await core.process({"action": "get_agent", "agent_id": aid})
    b = await core.process({"action": "get_agent",
                            "agent_id": imported["data"]["agent_id"]})
    assert a["data"]["nodes"] == b["data"]["nodes"]
    assert a["data"]["ledger_events"] == b["data"]["ledger_events"]


# --- NG5 never raises -------------------------------------------------------- #
@pytest.mark.parametrize("bad", [None, [], "x", 5])
async def test_NG5_nondict_input_never_raises(core, bad):
    r = await core.process(bad)
    assert r["status"] == "error"
    assert r["field"] == "input_data"


async def test_NG5_out_of_range_score_is_validation_error(core):
    aid = await _create(core)
    r = await core.process({"action": "submit_evaluation", "agent_id": aid,
                            "evaluation": {"task_id": "t", "task_type": "x",
                                           "success_score": 7.0}})
    assert r["status"] == "error"
    assert r["error_type"] == "ValidationError"


async def test_NG5_unknown_agent_teaches(core):
    r = await core.process({"action": "get_agent", "agent_id": "ng_999999"})
    assert r["status"] == "error"
    assert "create_agent" in r["constraint"]


# --- NG6 deterministic evolution --------------------------------------------- #
async def test_NG6_same_sequence_same_outcome(core):
    a = await _create(core)
    b = await _create(core)
    for aid in (a, b):
        for i in range(3):
            await core.process({"action": "submit_evaluation",
                                "agent_id": aid,
                                "evaluation": {**EVAL_OK,
                                               "task_id": f"t{i}"}})
    ga = await core.process({"action": "get_agent", "agent_id": a})
    gb = await core.process({"action": "get_agent", "agent_id": b})
    assert ga["data"]["nodes"] == gb["data"]["nodes"]
    assert ga["data"]["edges"] == gb["data"]["edges"]


async def test_routing_and_lifecycle(core):
    aid = await _create(core)
    await core.process({"action": "submit_evaluation", "agent_id": aid,
                        "evaluation": EVAL_OK})
    steps = await core.process({"action": "best_next_steps", "agent_id": aid,
                                "from_node": "planner"})
    assert steps["status"] == "ok"
    listing = await core.process({"action": "list_agents"})
    assert listing["data"]["count"] == 1
    deleted = await core.process({"action": "delete_agent", "agent_id": aid})
    assert deleted["data"]["deleted"] is True
    assert (await core.process({"action": "list_agents"}))["data"]["count"] == 0


async def test_survives_gateway_module_eviction(core):
    """REGRESSION (observed live 2026-07-18): the gateway evicts src.*
    modules after each adapter loads (PS8 isolation). Any function-level
    relative import inside the vendored engine then re-resolves 'src.vg'
    at CALL time and crashes. All engine imports must be module-level."""
    import sys
    aid = await _create(core)
    evicted = {m: sys.modules.pop(m) for m in list(sys.modules)
               if m == "src" or m.startswith("src.")}
    try:
        r = await core.process({"action": "submit_evaluation",
                                "agent_id": aid, "evaluation": EVAL_OK})
        assert r["status"] == "ok", r
        assert r["data"]["evaluation_accepted"] is True
    finally:
        sys.modules.update(evicted)


async def test_unknown_action_and_health(core):
    r = await core.process({"action": "photosynthesize"})
    assert r["status"] == "error" and "create_agent" in r["constraint"]
    h = await core.health()
    assert h["status"] == "ok" and "agents" in h["checks"]
