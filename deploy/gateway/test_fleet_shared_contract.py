import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PAID_TOOLS = {
    "smartscale-agent": {"scale_objects_from_credit_card"},
    "protogen-agent": {
        "create_cad_workspace", "generate_cad_design",
        "manufacturing_plan_from_spec",
    },
    "taxcredit-engine-agent": {"calculate_tax_credit"},
    "ghg-ledger-agent": {"calculate_inventory"},
    "quantity-takeoff-agent": {"calculate_takeoff"},
    "disclosure-compiler-agent": {"compile_disclosure"},
    "narrative-engine-agent": {"translate_narrative"},
    "regulatory-radar-agent": {
        "scan_regulations", "assess_compliance", "monitor_changes",
    },
    "agent-verified-relay-agent": {"register_service", "call_verified"},
    "verdigraph-brain-agent": {"build_brain"},
    "neurogenesis-agent": {
        "create_agent", "submit_evaluation", "import_state", "delete_agent",
        "register_compute_profile", "route_task", "record_route_outcome",
    },
    "green-router-agent": {"certify"},
    "agent-hive-orchestrator-agent": {"solve"},
}


def _function_args(agent_dir):
    path = ROOT / agent_dir / "adapters" / "mcp_server.py"
    tree = ast.parse(path.read_text())
    return {
        node.name: {arg.arg for arg in node.args.args}
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_every_paid_mcp_tool_exposes_retry_id():
    for agent_dir, paid_tools in PAID_TOOLS.items():
        functions = _function_args(agent_dir)
        assert paid_tools <= functions.keys()
        for tool in paid_tools:
            assert "request_id" in functions[tool], f"{agent_dir}:{tool}"


def test_edge_and_gateway_body_limits_are_both_present():
    caddy = (ROOT / "deploy/droplet/Caddyfile").read_text()
    assert "request_body" in caddy
    assert "max_size 1MB" in caddy
    middleware = (ROOT / "deploy/gateway/request_limits.py").read_text()
    assert "1_000_000" in middleware
    assert "MAX_REQUEST_BODY_BYTES" in middleware


def test_production_requirements_are_exactly_pinned_and_locked():
    requirements = (
        ROOT / "deploy/gateway/requirements.txt"
    ).read_text().splitlines()
    active = [line for line in requirements if line and not line.startswith("#")]
    assert active
    assert all("==" in line and ">=" not in line for line in active)
    lock = (ROOT / "deploy/gateway/requirements.lock").read_text().splitlines()
    locked = [line for line in lock if line and not line.startswith("#")]
    assert locked
    assert all("==" in line and ">=" not in line for line in locked)


def test_smartscale_publish_schema_is_structured_in_both_trees():
    for tree in ("mcp-publish", "mcp-publish-github"):
        manifest = json.loads((
            ROOT / "deploy" / tree / "smartscale-agent" / "tools.json"
        ).read_text())
        assert manifest["tool_count"] == len(manifest["tools"])
        for tool in manifest["tools"]:
            assert tool["outputSchema"]["type"] == "object"
            assert "status" in tool["outputSchema"]["required"]
