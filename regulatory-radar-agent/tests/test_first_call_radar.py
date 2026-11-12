"""FC1 and J1/J2 for the regulatory radar.

FC1  the published example returns regulations; a failed scan is handed it
J1   common spellings of a covered jurisdiction or sector are accepted
J2   a place inside a covered jurisdiction is answered for that jurisdiction,
     and the response says what was read and what is not covered
"""
import asyncio
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]

from src import core  # noqa: E402
from src.validation import normalize_jurisdiction, normalize_sector  # noqa: E402

ENGINE = core.RegulatoryRadarCore()


def run(**request):
    return asyncio.run(ENGINE.process({"action": "scan", **request}))


def regulations(response):
    return response["regulations"] if "regulations" in response \
        else response["data"]["regulations"]


def test_fc1_published_example_returns_regulations_without_help():
    got = run(**core.EXAMPLE_REQUEST)
    assert got["status"] != "error"
    assert len(regulations(got)) > 0
    assert "first_call_help" not in got and "input_read_as" not in got


@pytest.mark.parametrize("request_", [
    {}, {"jurisdiction": ""}, {"jurisdiction": "Mars"},
    {"jurisdiction": "us", "sector": "space_mining"},
])
def test_fc1_failed_scan_is_handed_the_working_example(request_):
    got = run(**request_)
    assert got["status"] == "error" and got["error_type"] == "ValidationError"
    help_ = got["first_call_help"]
    assert help_["example_request"] == core.EXAMPLE_REQUEST
    assert "california" in help_["jurisdictions"] and "energy" in help_["sectors"]
    retry = run(**help_["example_request"])
    assert retry["status"] != "error" and regulations(retry)


def test_fc1_description_and_describe_carry_the_same_example():
    assert ENGINE.describe()["example_request"] == core.EXAMPLE_REQUEST
    import adapters.mcp_server as adapter
    fn = getattr(adapter.scan_regulations, "fn", adapter.scan_regulations)
    doc = inspect.getdoc(inspect.unwrap(fn))
    assert json.loads(doc.split("Example arguments: ", 1)[1]) == core.EXAMPLE_REQUEST
    # a bare call must reach the engine's help, not die in schema validation
    assert inspect.signature(inspect.unwrap(fn)).parameters["jurisdiction"].default is None


@pytest.mark.parametrize("given,canonical", [
    ("USA", "us"), ("United States", "us"), ("  united   states ", "us"),
    ("European Union", "eu"), ("United Kingdom", "uk"), ("Canada", "ca"),
    ("CA", "ca"), ("California", "california"), ("us-ca", "california"),
])
def test_j1_spellings_of_a_covered_jurisdiction(given, canonical):
    assert normalize_jurisdiction(given) == canonical
    got = run(jurisdiction=given)
    assert got["status"] != "error" and "input_read_as" not in got


@pytest.mark.parametrize("given,canonical", [
    ("software", "technology"), ("Financial Services", "financial_services"),
    ("oil and gas", "energy"), ("consumer-goods", "consumer_goods"),
    ("forestry", "forestry"),
])
def test_j1_spellings_of_a_sector(given, canonical):
    assert normalize_sector(given) == canonical
    assert run(jurisdiction="us", sector=given)["status"] != "error"


@pytest.mark.parametrize("given,parent", [("Texas", "us"), ("New York", "us"),
                                          ("Germany", "eu"), ("france", "eu")])
def test_j2_a_place_inside_a_jurisdiction_is_answered_and_labelled(given, parent):
    got = run(jurisdiction=given)
    assert got["status"] != "error"
    reading = got["input_read_as"]["jurisdiction"]
    assert (reading["given"], reading["read_as"]) == (given, parent)
    assert "not in the dataset" in reading["note"]
    # identical regulations to asking for the covering jurisdiction directly
    direct = run(jurisdiction=parent)
    assert [r["id"] if "id" in r else r["name"] for r in regulations(got)] == \
        [r["id"] if "id" in r else r["name"] for r in regulations(direct)]


def test_j2_ambiguous_or_uncovered_places_are_refused_not_guessed():
    for place in ("Georgia", "Brazil", "India"):
        got = run(jurisdiction=place)
        assert got["status"] == "error" and "first_call_help" in got


def test_other_actions_and_evidence_packs_are_untouched():
    got = asyncio.run(ENGINE.process({"action": "no_such_action"}))
    assert got["status"] == "error" and "first_call_help" not in got


def test_rg5_validation_binds_applicability_at_import_time():
    """The gateway evicts `src*` modules between agent loads; a relative import
    inside a function would then resolve against another agent's package."""
    import ast
    import src.validation as validation
    assert hasattr(validation, "ENTITY_PROFILE_FIELDS")
    tree = ast.parse(Path(validation.__file__).read_text())
    late = [node.lineno for fn in ast.walk(tree)
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            for node in ast.walk(fn)
            if isinstance(node, ast.ImportFrom) and node.level > 0]
    assert late == [], late
