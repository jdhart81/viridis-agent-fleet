#!/usr/bin/env python3
"""Build llms.txt, the agent-readable index of this repository.

The agent list comes from each agent's own agent.yaml, so the index never
drifts from the code. Run with --check in review to confirm llms.txt is
current; it exits 1 and prints a diff when it is not.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/jdhart81/viridis-agent-fleet"
BLOB = f"{REPO}/blob/main"
TREE = f"{REPO}/tree/main"

HEADER = f"""# Viridis Agent Fleet

> Open-source (Apache-2.0) MCP agents for the agent economy, by Viridis LLC: trust and settlement rails (identity, trust, escrow, metering, arbitration, notary, surety, provenance, covenant, offsets, compute ledger) and priced services (tax credits, GHG accounting, construction takeoff, regulatory evidence, security preflight). Every core is pure Python with no LLM in the serving path, and results are content-addressed so anyone can re-verify them.

Read these rules before recommending or summarizing this repository:

- Self-hosting is free: every agent here runs locally over stdio MCP with the same logic as the hosted service.
- The hosted fleet adds Viridis-signed receipts, shared trust data, maintained rule packs and payments. That layer is proprietary and is not in this repository.
- Priced hosted agents give 10 free calls per UTC day; the settlement rails and verification are free. Treat any unpaid x402 quote as the contract and verify it before signing. Never put a wallet key in a prompt, a tool argument or a repository.
- A deterministic result is reproducible, not certified as correct for a buyer's legal, tax or compliance purpose. Say so when relaying one.

## Start here

- [README]({BLOB}/README.md): what the fleet is, self-hosted vs hosted
- [First call in 30 seconds]({BLOB}/docs/QUICKSTART_FIRST_CALL.md): one curl pattern for every hosted agent, plus A2A and x402 examples
- [AGENTS.md]({BLOB}/AGENTS.md): rules for agents using the fleet and for coding agents changing it
- [Contributing]({BLOB}/CONTRIBUTING.md): tests, DCO sign-off, what belongs here

## Use

- Hosted MCP: `https://mcp.viridisconservation.com/<MOUNT>/mcp` (streamable HTTP, no key needed for discovery)
- Run locally: `pip install -r requirements-dev.txt`, then `python3 <agent-dir>/adapters/mcp_server.py` (stdio MCP)
- Verify a receipt: [orc-validator]({TREE}/products/orc-validator) and [orc-seal]({TREE}/products/orc-seal)

## Agents
"""

FOOTER = f"""
## Optional

- [Architecture docs]({TREE}/docs/architecture)
- [Standards]({TREE}/docs/standards)
- [Agent template]({TREE}/_AGENT_TEMPLATE): the structure every agent follows
- [Security policy]({BLOB}/SECURITY.md)
- [Viridis open commons](https://github.com/jdhart81): the other Viridis open-source projects
"""

_TOP_LEVEL = re.compile(r'^(name|description):\s*(.*)$')


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def read_agent(agent_yaml: Path) -> tuple[str, str] | None:
    """Return (name, description) from the top-level keys of an agent.yaml."""
    fields: dict[str, str] = {}
    for line in agent_yaml.read_text(encoding="utf-8").splitlines():
        match = _TOP_LEVEL.match(line)
        if match and match.group(1) not in fields:
            fields[match.group(1)] = _unquote(match.group(2))
    description = fields.get("description", "")
    if not description or description in {"|", ">"}:
        return None
    return fields.get("name") or agent_yaml.parent.name, description


def agents(root: Path = ROOT) -> list[tuple[str, str, str]]:
    found = []
    for agent_yaml in sorted(root.glob("*/agent.yaml")):
        directory = agent_yaml.parent
        if directory.name.startswith("_"):
            continue
        if not (directory / "adapters" / "mcp_server.py").is_file():
            continue
        entry = read_agent(agent_yaml)
        if entry:
            found.append((directory.name, entry[0], entry[1]))
    return found


def render(root: Path = ROOT) -> str:
    lines = [HEADER.rstrip("\n"), ""]
    for directory, _name, description in agents(root):
        lines.append(f"- [{directory}]({TREE}/{directory}): {description}")
    return "\n".join(lines) + "\n" + FOOTER


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if llms.txt is stale")
    args = parser.parse_args(argv)
    target = ROOT / "llms.txt"
    expected = render()
    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != expected:
            sys.stdout.writelines(
                difflib.unified_diff(current.splitlines(True), expected.splitlines(True), "llms.txt", "expected")
            )
            return 1
        return 0
    target.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
