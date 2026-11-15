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


# ---- RH2 / SB 253: a California scan ends in a complete first-cycle draft ----
def test_california_scan_names_the_sb253_draft_and_the_chain_completes_it():
    scan = engine("regulatory-radar", {"action": "scan", "jurisdiction": "california",
                                       "sector": "energy"})["response"]
    body = scan.get("data", scan)
    step = body["next_calls"][0]
    then = step["then"]
    assert (then["agent"], then["tool"], then["framework"]) == (
        "disclosure-compiler", "compile_disclosure", "ca-sb253")
    assert then["because"] in step["because"] and then["because"] in {r["id"] for r in body["regulations"]}

    inventory = follow(step, scan)["response"]
    to_draft = inventory["next_calls"][0]
    # the agent does what `then.why` says: same request, this framework
    arguments = json.loads(json.dumps(to_draft["arguments"]))
    arguments["framework"] = then["framework"]
    arguments["options"]["applicability"] = {
        "framework": then["framework"], "applies": True,
        "reason": "entity does business in California with revenue over $1 billion"}
    draft = follow({**to_draft, "arguments": arguments}, inventory)["response"]
    assert draft["status"] == "ok", draft
    data = draft["data"]
    assert data["framework"]["id"] == "ca-sb253"
    assert data["draft_status"] == "complete" and not data["gaps"]
    filled = {item["id"]: item for item in data["filled_datapoints"]}
    assert {"entity_name", "reporting_period", "gross_scope_1",
            "gross_scope_2_location_based"} <= set(filled)
    # encouraged datapoints are filled from the inventory's own lineage, never invented
    assert filled["emission_factor_sources"]["value"] == inventory["data"]["lineage"]["source_ids_used"]
    assert filled["gwp_values"]["value"] == inventory["data"]["factor_pack"]["gwp_set_id"]
    assert "gross_scope_3" not in filled and "assurance_status" not in filled
    assert data["label"] == "disclosure draft for professional review"


def test_every_framework_a_scan_can_name_exists_in_the_compiler():
    listed = engine("disclosure-compiler", {"action": "list_frameworks"})["response"]
    known = {item["id"] for item in listed.get("data", listed)["frameworks"]}
    sys.path.insert(0, str(FLEET / "regulatory-radar-agent"))
    source = (FLEET / "regulatory-radar-agent" / "src" / "core.py").read_text()
    import re
    block = re.search(r"_DRAFT_FOR_RULE = \((.*?)\n\)", source, re.S).group(1)
    named = set(re.findall(r'"\s*,\s*"([a-z0-9\-]+)"\)', block))
    assert named and named <= known


def test_a_scan_outside_california_names_no_sb253_draft():
    scan = engine("regulatory-radar", {"action": "scan", "jurisdiction": "eu"})["response"]
    for step in scan.get("data", scan).get("next_calls", []):
        assert step.get("then", {}).get("framework") != "ca-sb253"


# ---- GH6 revised: a real single-year inventory computes and drafts ----
def test_a_fiscal_2025_inventory_computes_and_fills_the_sb253_draft():
    activities = [
        {"id": "elec", "activity_type": "purchased_electricity", "quantity": 480000.5,
         "unit": "kWh", "region": "US-CAMX", "year": 2025},
        {"id": "gas", "activity_type": "stationary_combustion_natural_gas", "quantity": 12000,
         "unit": "therms", "region": "US", "year": 2025},
    ]
    inventory = engine("ghg-ledger", {"action": "calculate_inventory", "activities": activities})["response"]
    data = inventory["data"]
    assert data["inventory_status"] == "complete_for_supplied_activities"
    assert data["factor_vintage_notes"] == [
        {"id": "elec", "factor_id": "epa_egrid2023_camx_ar6", "activity_year": 2025, "factor_year": 2023}]
    assert data["inputs"]["activities"][0]["quantity"] == "480000.5"      # audited as text, not a float
    to_draft = inventory["next_calls"][0]
    arguments = json.loads(json.dumps(to_draft["arguments"]))
    arguments["framework"] = "ca-sb253"
    arguments["options"]["applicability"] = {"framework": "ca-sb253", "applies": True,
                                             "reason": "scenario entity in scope"}
    draft = follow({**to_draft, "arguments": arguments}, inventory)["response"]
    assert draft["status"] == "ok", draft
    assert draft["data"]["draft_status"] == "complete"
