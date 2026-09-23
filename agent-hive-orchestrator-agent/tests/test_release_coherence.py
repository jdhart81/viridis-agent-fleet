import json
import re
from pathlib import Path

from src.core import VERSION


ROOT = Path(__file__).resolve().parents[2]


def test_hive_release_versions_are_coherent_across_private_and_public_layouts():
    yaml_text = (
        ROOT / "agent-hive-orchestrator-agent" / "agent.yaml").read_text()
    match = re.search(
        r'(?m)^version:\s*["\']?([^"\'\s#]+)', yaml_text)
    assert match is not None
    assert match.group(1) == VERSION

    for manifest_root in ("mcp-publish", "mcp-publish-github"):
        candidates = (
            ROOT / "deploy" / manifest_root
            / "agent-hive-orchestrator-agent" / "server.json",
            ROOT / manifest_root
            / "agent-hive-orchestrator-agent" / "server.json",
        )
        path = next((item for item in candidates if item.is_file()), None)
        assert path is not None
        assert json.loads(path.read_text())["version"] == VERSION
