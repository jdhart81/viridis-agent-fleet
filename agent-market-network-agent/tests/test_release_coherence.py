import json
import re
from pathlib import Path

from src.core import VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_agent_market_release_versions_are_coherent():
    yaml_text = (ROOT / "agent-market-network-agent" / "agent.yaml").read_text()
    match = re.search(
        r'(?m)^version:\s*["\']?([^"\'\s#]+)', yaml_text)
    assert match is not None
    assert match.group(1) == VERSION

    candidates = (
        ROOT / "deploy" / "mcp-publish-github"
        / "agent-market-network-agent" / "server.json",
        ROOT / "mcp-publish-github"
        / "agent-market-network-agent" / "server.json",
    )
    server_path = next((path for path in candidates if path.is_file()), None)
    assert server_path is not None
    server = json.loads(server_path.read_text())
    assert server["version"] == VERSION
    assert "verified escrow funding" in server["description"].lower()
