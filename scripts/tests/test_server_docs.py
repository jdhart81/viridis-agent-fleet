"""SD1-SD7: every MCP Registry entry has a complete, current docs page."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import server_docs as sd  # noqa: E402

SNAPSHOT = json.loads(sd.SNAPSHOT.read_text())
# Ratchets: may shrink, never grow. agent-market-network runs in its own
# container (not the gateway), so the gateway's argument descriptions do not
# reach it yet.
UNDESCRIBED_SERVERS: set = set()   # empty since market 0.8.2 (Nov 16)


def test_sd1_one_page_per_registry_entry():
    entries = sd.registry_entries()
    assert len(entries) >= 30
    for entry in entries:
        assert (sd.OUT / f"{entry['short']}.md").exists(), entry["name"]
        assert entry["name"] in SNAPSHOT["servers"], entry["name"]


def test_sd2_every_tool_and_input_is_on_its_page():
    for entry in sd.registry_entries():
        page = (sd.OUT / f"{entry['short']}.md").read_text()
        tools = SNAPSHOT["servers"][entry["name"]]["tools"]
        assert tools, entry["name"]
        for tool in tools:
            assert f"### `{tool['name']}`" in page, (entry["name"], tool["name"])
            for arg, prop in ((tool.get("inputSchema") or {}).get("properties") or {}).items():
                assert f"| `{arg}` |" in page, (entry["name"], tool["name"], arg)
                if entry["name"] not in UNDESCRIBED_SERVERS:
                    assert str(prop.get("description") or "").strip(), (entry["name"], tool["name"], arg)


def test_sd3_examples_are_real_answers():
    missing = []
    for entry in sd.registry_entries():
        record = SNAPSHOT["servers"][entry["name"]]
        example = record.get("example")
        if not example:
            missing.append(entry["name"])
            continue
        names = {t["name"] for t in record["tools"]}
        assert example["tool"] in names
        try:
            answer = json.loads(example["response"])
        except ValueError:
            continue
        if isinstance(answer, dict):
            assert answer.get("status") != "error" and not answer.get("error"), entry["name"]
    assert missing == [], missing


def test_sd5_connection_payment_and_ownership_on_every_page():
    for entry in sd.registry_entries():
        page = (sd.OUT / f"{entry['short']}.md").read_text()
        for needle in (entry["url"], "## Connect", "## Pricing and authentication",
                       "## Hosted service and this repository", "ViridisNorth LLC",
                       "../HOSTED_MCP.md"):
            assert needle in page, (entry["name"], needle)


def test_sd6_sd7_pages_and_readme_index_are_current():
    assert sd.build(write=False) == []
