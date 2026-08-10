"""Portable source-contract checks for the public Neurogenesis mount."""

import ast
from pathlib import Path
import sys


AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.core import NeurogenesisCore  # noqa: E402


def _function_arguments() -> dict[str, set[str]]:
    tree = ast.parse((AGENT_ROOT / "adapters/mcp_server.py").read_text())
    return {
        node.name: {argument.arg for argument in node.args.args}
        for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
    }


def test_wu_wei_mutations_expose_retry_ids():
    arguments = _function_arguments()
    for tool in (
        "register_compute_profile", "route_task", "record_route_outcome",
    ):
        assert "request_id" in arguments[tool]


def test_outcomes_are_known_mutations_and_reports_are_reads():
    assert "record_route_outcome" in NeurogenesisCore.KNOWN_ACTIONS
    assert "record_route_outcome" not in NeurogenesisCore.READ_ACTIONS
    assert "compute_efficiency_report" in NeurogenesisCore.READ_ACTIONS
