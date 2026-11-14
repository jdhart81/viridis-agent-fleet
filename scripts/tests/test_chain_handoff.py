"""CH1: fleet results hand the caller the next call, and the hand-off works.

An agent that follows only what the responses say goes from a disclosure draft
with emission gaps, to a GHG inventory, back to a draft with those gaps filled.
Each engine runs in its own process, as it does behind the gateway.
"""
import json
import subprocess
import sys
from pathlib import Path

FLEET = Path(__file__).resolve().parents[2]
DIRS = {"ghg-ledger": "ghg-ledger-agent", "disclosure-compiler": "disclosure-compiler-agent",
        "regulatory-radar": "regulatory-radar-agent"}
RUN = r"""
import asyncio, json, sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from src import core
request = json.loads(sys.stdin.read())
build = getattr(core, "build", None) or getattr(core, "RegulatoryRadarCore")
print(json.dumps({"response": asyncio.run(build().process(request)),
                  "example": core.EXAMPLE_REQUEST}, default=str))
"""


def engine(agent, request):
    out = subprocess.run([sys.executable, "-c", RUN, str(FLEET / DIRS[agent]), str(FLEET)],
                         input=json.dumps(request), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def follow(step, this_response):
    """Send a next_calls entry exactly as written, resolving its one reference."""
    def resolve(value):
        if value == {"$ref": "this_response.data"}:
            return this_response["data"]
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        return value
    return engine(step["agent"], {"action": step["tool"], **resolve(step["arguments"])})


def gap_ids(response):
    return {g["status"].removeprefix("MISSING: ") for g in response["data"]["gaps"]}


def test_draft_to_inventory_to_filled_draft_using_only_the_responses():
    start = engine("disclosure-compiler", {"action": "compile_disclosure"})["example"]
    draft = engine("disclosure-compiler", {"action": "compile_disclosure", **start})["response"]
    assert {"gross_scope_1", "gross_scope_2_location_based"} <= gap_ids(draft)

    to_inventory = draft["next_calls"][0]
    assert (to_inventory["agent"], to_inventory["tool"]) == ("ghg-ledger", "calculate_inventory")
    inventory = follow(to_inventory, draft)["response"]
    assert inventory["data"]["inventory_status"] == "complete_for_supplied_activities"

    to_draft = inventory["next_calls"][0]
    assert (to_draft["agent"], to_draft["tool"]) == ("disclosure-compiler", "compile_disclosure")
    filled = follow(to_draft, inventory)["response"]
    assert filled["status"] == "ok"
    assert not {"gross_scope_1", "gross_scope_2_location_based"} & gap_ids(filled)
    values = {p["id"]: p["value"] for p in filled["data"]["filled_datapoints"]}
    assert values["gross_scope_1"] not in (None, "", "0.000000")
    # the chain ends: a draft built from an inventory does not ask for one again
    assert "next_calls" not in filled


def test_handoff_arguments_are_the_other_engines_published_example():
    ghg = engine("ghg-ledger", {"action": "calculate_inventory"})
    disclosure = engine("disclosure-compiler", {"action": "compile_disclosure"})
    draft = engine("disclosure-compiler",
                   {"action": "compile_disclosure", **disclosure["example"]})["response"]
    assert draft["next_calls"][0]["arguments"] == ghg["example"]
    inventory = engine("ghg-ledger",
                       {"action": "calculate_inventory", **ghg["example"]})["response"]
    sent = dict(inventory["next_calls"][0]["arguments"])
    assert sent.pop("ghg_result") == {"$ref": "this_response.data"}
    assert sent == disclosure["example"]


def test_handoff_sits_beside_data_and_only_on_computed_results():
    ghg_example = engine("ghg-ledger", {"action": "calculate_inventory"})["example"]
    inventory = engine("ghg-ledger",
                       {"action": "calculate_inventory", **ghg_example})["response"]
    assert "next_calls" not in inventory["data"]
    verdict = engine("ghg-ledger",
                     {"action": "verify_result", "result": inventory["data"]})["response"]
    assert verdict["status"] == "ok" and verdict["data"]["valid"] is True
    failed = engine("ghg-ledger", {"action": "calculate_inventory",
                                   "activities": [{"type": "electricity"}],
                                   "options": {}})["response"]
    assert "next_calls" not in failed and "first_call_help" in failed


# ---- RH1: a regulatory scan hands on to the inventory, and on to a draft (E4) ----
def test_scan_to_inventory_to_draft_using_only_the_responses():
    radar = engine("regulatory-radar", {"action": "scan"})
    scan = engine("regulatory-radar", {"action": "scan", **radar["example"]})["response"]
    body = scan.get("data", scan)
    assert body["total_regulations"] > 0

    to_inventory = body["next_calls"][0]
    assert (to_inventory["agent"], to_inventory["tool"]) == ("ghg-ledger", "calculate_inventory")
    listed = {r["id"] for r in body["regulations"]}
    assert to_inventory["because"] and set(to_inventory["because"]) <= listed
    assert to_inventory["replace_before_sending"] == ["activities"]

    inventory = follow(to_inventory, scan)["response"]
    assert inventory["status"] == "ok"
    assert inventory["data"]["inventory_status"] == "complete_for_supplied_activities"

    to_draft = inventory["next_calls"][0]
    assert (to_draft["agent"], to_draft["tool"]) == ("disclosure-compiler", "compile_disclosure")
    draft = follow(to_draft, inventory)["response"]
    assert draft["status"] == "ok"
    assert not {"gross_scope_1", "gross_scope_2_location_based"} & gap_ids(draft)


def test_scan_hand_off_request_is_the_ledgers_own_published_example():
    radar = engine("regulatory-radar", {"action": "scan"})
    scan = engine("regulatory-radar", {"action": "scan", **radar["example"]})["response"]
    step = scan.get("data", scan)["next_calls"][0]
    ledger = engine("ghg-ledger", {"action": "calculate_inventory"})["example"]
    assert step["arguments"] == ledger


def test_scan_with_no_emissions_rule_offers_no_inventory_hand_off():
    empty = engine("regulatory-radar", {"action": "scan", "jurisdiction": "US",
                                        "query": "zzzqqq"})["response"]
    assert "next_calls" not in empty.get("data", empty)
