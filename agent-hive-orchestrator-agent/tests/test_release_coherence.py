import json
import re
from pathlib import Path

import pytest

from src.core import VERSION


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_MANIFEST_PRESENT = any(
    (ROOT / path / "agent-hive-orchestrator-agent" / "server.json").is_file()
    for path in ("deploy/mcp-publish", "deploy/mcp-publish-github",
                 "mcp-publish", "mcp-publish-github")
)


@pytest.mark.skipif(not PRIVATE_MANIFEST_PRESENT,
                    reason="private release manifest layout is absent")
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
        manifest = json.loads(path.read_text())
        # a hosted listing records the open-core release it builds on
        recorded = (manifest.get("_meta", {})
                    .get("io.modelcontextprotocol.registry/publisher-provided", {})
                    .get("viridis", {}).get("release"))
        assert (recorded or manifest["version"]) == VERSION
