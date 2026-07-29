"""EnergyAI federation discovery and health-response invariants."""
from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import viridis_mcp_gateway as gateway  # noqa: E402


def _energyai_member() -> dict:
    return next(
        member for member in gateway.EXTERNAL_MEMBERS
        if member["identifier"] == "urn:air:viridis:energyai")


def test_energyai_federation_matches_live_v1_contract():
    member = _energyai_member()
    assert member["url"] == "https://api.energyaisolution.com/mcp"
    assert member["version"] == "1.0.0"
    assert member["capabilities"] == [
        "check_incentives",
        "estimate_production",
        "get_node_score",
        "get_quote_link",
        "route_lead",
        "list_guides",
        "get_guide",
        "find_local_installers",
    ]
    activation = member["metadata"]["builderActivation"]
    assert activation["firstCommercialTool"] == "bootstrap_energy_project"
    assert activation["trialCommercialCalls"] == 3
    assert activation["cardRequiredForTrial"] is False
    assert activation["monthlyPriceUsd"] == 19
    assert activation["monthlyCreditUsd"] == 20


def test_mcp_tool_parser_counts_tools_not_schema_name_fields():
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": [
                {
                    "name": "check_incentives",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "zip": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    },
                },
                {"name": "find_local_installers", "inputSchema": {}},
            ],
        },
    }
    expected = {"check_incentives", "find_local_installers"}
    assert gateway._mcp_tool_names(json.dumps(payload)) == expected
    assert gateway._mcp_tool_names(
        "event: message\ndata: " + json.dumps(payload) + "\n\n") == expected
    assert gateway._mcp_tool_names('{"result":{"not_tools":[]}}') is None
