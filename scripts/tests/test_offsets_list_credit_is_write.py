"""list_credit adds a credit to the clearinghouse book, so its MCP annotation
must not claim read-only (directories and agents trust readOnlyHint, and the
hosted gateway's credential gate checks it against its open list)."""
import ast
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[2] / "agent-offset-clearinghouse-agent" / "adapters" / "mcp_server.py"


def test_list_credit_is_annotated_as_a_write():
    tree = ast.parse(ADAPTER.read_text())
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_credit":
            kinds = [kw.value.id for d in node.decorator_list if isinstance(d, ast.Call)
                     for kw in d.keywords if kw.arg == "annotations" and isinstance(kw.value, ast.Name)]
            assert kinds == ["_WRITE"]
            return
    raise AssertionError("list_credit tool not found")
